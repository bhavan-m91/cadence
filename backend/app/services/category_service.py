"""Category tree: one primary category per activity partitions the 24 hours (FR-085..FR-090, D-02)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import rolls_back_on_error
from app.core.errors import AppError, Conflict, NotFound, ValidationFailed
from app.models import Category, User
from app.models.enums import RootKind
from app.repositories.taxonomy import TaxonomyRepository
from app.repositories.users import UsersRepository
from app.schemas.taxonomy import CategoryCreate, CategoryMergeOut, CategoryNode, CategoryOut, CategoryPatch

PALETTE = ["#3E86D4", "#1C9C8D", "#8A6CE6", "#DB5E86", "#C27C22", "#2E9E6B", "#5E6582", "#4C63E6"]
ROOTS = [("Work", RootKind.work, "#4C63E6"), ("Personal", RootKind.personal, "#1C9C8D"), ("Sleep", RootKind.sleep, "#5E6582")]
MAX_DEPTH = 3


def category_out(c: Category) -> CategoryOut:
    o = CategoryOut.model_validate(c)
    o.archived = c.archived_at is not None
    return o


def build_tree(categories: list[Category]) -> list[CategoryNode]:
    nodes = {c.id: CategoryNode(**category_out(c).model_dump()) for c in categories}
    roots: list[CategoryNode] = []
    for c in categories:
        node = nodes[c.id]
        if c.parent_id and c.parent_id in nodes:
            nodes[c.parent_id].children.append(node)
        elif c.parent_id is None:
            roots.append(node)
    return roots


async def ensure_roots(session: AsyncSession, user_id: uuid.UUID) -> dict[RootKind, Category]:
    """The three system roots exist for every user (FR-085). Idempotent."""
    repo = TaxonomyRepository(session, user_id)
    out: dict[RootKind, Category] = {}
    for i, (name, kind, color) in enumerate(ROOTS):
        root = await repo.root(kind)
        if root is None:
            cid = uuid.uuid4()
            root = Category(id=cid, user_id=user_id, parent_id=None, root_kind=kind, depth=1, name=name, path_ids=[cid],
                            path_names=name, color=color, is_system=True, sort_order=i)
            session.add(root)
        out[kind] = root
    await session.flush()
    return out


class CategoryService:
    def __init__(self, session: AsyncSession, user: User):
        self.session, self.user = session, user
        self.repo = TaxonomyRepository(session, user.id)

    async def _get(self, category_id: uuid.UUID, *, for_update: bool = False) -> Category:
        c = await self.repo.category(category_id, for_update=for_update)
        if c is None:
            raise NotFound("Category not found")
        return c

    async def _finish(self) -> None:
        try:
            await self.session.flush()
            await UsersRepository(self.session).bump_revision(self.user.id)
            await self.session.commit()
        except IntegrityError as e:
            await self.session.rollback()
            if "categories_sibling_name_uq" in str(e.orig):
                raise Conflict("A category with that name already exists here", code="NAME_TAKEN") from e
            raise

    async def tree(self, include_archived: bool = False) -> list[CategoryNode]:
        return build_tree(await self.repo.categories(include_archived))

    @rolls_back_on_error
    async def create(self, body: CategoryCreate) -> CategoryOut:
        parent = await self._get(body.parent_id)
        if parent.archived_at is not None:
            raise ValidationFailed("Parent category is archived", path="parent_id", rule="archived")
        if parent.depth >= MAX_DEPTH:
            raise AppError("Categories can be at most 3 levels deep", code="CATEGORY_DEPTH_EXCEEDED", status=422)
        if await self.repo.sibling_name_taken(parent.id, body.name):
            raise Conflict("A category with that name already exists here", code="NAME_TAKEN")
        cid = uuid.uuid4()
        siblings = await self.repo.children(parent.id)
        c = Category(
            id=cid, user_id=self.user.id, parent_id=parent.id, root_kind=parent.root_kind, depth=parent.depth + 1, name=body.name,
            path_ids=[*parent.path_ids, cid], path_names=f"{parent.path_names} › {body.name}",
            color=body.color or PALETTE[len(await self.repo.categories(True)) % len(PALETTE)], description=body.description,
            counts_as_focus=body.counts_as_focus, is_transition=body.is_transition, sort_order=len(siblings),
        )
        self.session.add(c)
        await self._finish()
        return category_out(c)

    @rolls_back_on_error
    async def update(self, category_id: uuid.UUID, body: CategoryPatch) -> CategoryOut:
        c = await self._get(category_id, for_update=True)
        fields = body.model_fields_set
        if c.is_system and (body.name is not None or "parent_id" in fields and body.parent_id is not None or body.archived):
            raise Conflict("System categories cannot be renamed, moved or archived", code="CATEGORY_SYSTEM")
        subtree = await self.repo.subtree(c)

        if body.parent_id is not None and body.parent_id != c.parent_id:
            await self._move(c, subtree, body.parent_id)
        if body.name is not None and body.name != c.name:
            if await self.repo.sibling_name_taken(c.parent_id, body.name, c.id):
                raise Conflict("A category with that name already exists here", code="NAME_TAKEN")
            self._rename_paths(c, subtree, body.name)
        for f in ("color", "description", "counts_as_focus", "is_transition", "sort_order"):
            v = getattr(body, f)
            if v is not None:
                setattr(c, f, v)
        if body.archived is not None:
            await self._archive(c, subtree, body.archived)
        await self._finish()
        return category_out(c)

    def _rename_paths(self, c: Category, subtree: list[Category], new_name: str) -> None:
        """Rename `c` and rewrite the stored path text of its descendants."""
        old_prefix = c.path_names
        parent_prefix = old_prefix.rsplit(" › ", 1)[0] if c.depth > 1 else ""
        c.name = new_name
        new_prefix = f"{parent_prefix} › {new_name}" if parent_prefix else new_name
        for x in subtree:
            if x.id == c.id:
                x.path_names = new_prefix
            else:
                x.path_names = new_prefix + x.path_names[len(old_prefix):]

    async def _move(self, c: Category, subtree: list[Category], new_parent_id: uuid.UUID) -> None:
        parent = await self._get(new_parent_id)
        if parent.id == c.id or c.id in parent.path_ids:
            raise AppError("A category cannot be moved under itself", code="CATEGORY_CYCLE", status=422)
        if parent.archived_at is not None:
            raise ValidationFailed("Target parent is archived", path="parent_id", rule="archived")
        height = max(x.depth for x in subtree) - c.depth + 1
        if parent.depth + height > MAX_DEPTH:
            raise AppError("Categories can be at most 3 levels deep", code="CATEGORY_DEPTH_EXCEEDED", status=422)
        if parent.root_kind != c.root_kind and await self.repo.any_activity_for_categories([x.id for x in subtree]):
            raise AppError("Categories with activities cannot move to another root", code="CROSS_ROOT_MOVE", status=422)
        if await self.repo.sibling_name_taken(parent.id, c.name, c.id):
            raise Conflict("A category with that name already exists there", code="NAME_TAKEN")
        c.parent_id = parent.id
        c.path_ids, c.path_names, c.depth, c.root_kind = [*parent.path_ids, c.id], f"{parent.path_names} › {c.name}", parent.depth + 1, parent.root_kind
        self._repath_descendants(c, subtree)

    def _repath_descendants(self, c: Category, subtree: list[Category]) -> None:
        by_parent: dict[uuid.UUID, list[Category]] = {}
        for x in subtree:
            if x.parent_id and x.id != c.id:
                by_parent.setdefault(x.parent_id, []).append(x)

        def walk(node: Category) -> None:
            for child in by_parent.get(node.id, []):
                child.path_ids = [*node.path_ids, child.id]
                child.path_names = f"{node.path_names} › {child.name}"
                child.depth = node.depth + 1
                child.root_kind = node.root_kind
                walk(child)

        walk(c)

    async def _archive(self, c: Category, subtree: list[Category], archive: bool) -> None:
        if archive:
            if await self.repo.active_allocations([x.id for x in subtree]):
                raise Conflict("An active Ideal allocation uses this category", code="CATEGORY_ALLOCATED")
            now = datetime.now(UTC)
            for x in subtree:
                if x.archived_at is None:
                    x.archived_at = now
        else:
            if c.parent_id:
                parent = await self._get(c.parent_id)
                if parent.archived_at is not None:
                    raise ValidationFailed("Unarchive the parent first", path="archived", rule="parent_archived")
            c.archived_at = None

    @rolls_back_on_error
    async def delete(self, category_id: uuid.UUID) -> None:
        c = await self._get(category_id, for_update=True)
        if c.is_system:
            raise Conflict("System categories cannot be deleted", code="CATEGORY_SYSTEM")
        if await self.repo.children(c.id):
            raise Conflict("Move or delete the child categories first", code="CATEGORY_HAS_CHILDREN")
        if await self.repo.any_activity_for_categories([c.id]):
            raise Conflict("This category has activities; merge or reassign first", code="CATEGORY_IN_USE")
        if await self.repo.any_allocation(c.id):
            raise Conflict("An Ideal allocation uses this category", code="CATEGORY_ALLOCATED")
        await self.session.delete(c)
        await self._finish()

    @rolls_back_on_error
    async def merge(self, source_id: uuid.UUID, target_id: uuid.UUID, preview: bool) -> CategoryMergeOut:
        src = await self._get(source_id, for_update=True)
        tgt = await self._get(target_id, for_update=True)
        if src.is_system:
            raise Conflict("System categories cannot be merged away", code="CATEGORY_SYSTEM")
        if src.id == tgt.id or src.id in tgt.path_ids:
            raise AppError("Choose a different target (not itself or a descendant)", code="INVALID_MERGE_TARGET", status=422)
        if src.root_kind != tgt.root_kind:
            raise AppError("Categories can only be merged within one root", code="CROSS_ROOT_MERGE", status=422)
        if tgt.archived_at is not None:
            raise AppError("The target category is archived", code="INVALID_MERGE_TARGET", status=422)
        subtree = await self.repo.subtree(src)
        children = [x for x in subtree if x.parent_id == src.id]
        height = (max(x.depth for x in subtree) - src.depth)  # levels below src
        if height and tgt.depth + height > MAX_DEPTH:
            raise AppError("Merging would make the tree deeper than 3 levels", code="CATEGORY_DEPTH_EXCEEDED", status=422)
        moved_activities = await self.repo.activity_count_for_categories([src.id])
        allocations = await self.repo.active_allocations([src.id])
        if preview:
            return CategoryMergeOut(moved_activities=moved_activities, moved_allocations=len(allocations), preview=True)

        await self.repo.repoint_activities([src.id], tgt.id)
        moved_alloc = await self.repo.move_allocations(src.id, tgt.id)
        await self.repo.move_keyword_rules(src.id, tgt.id)
        for ch in children:
            if await self.repo.sibling_name_taken(tgt.id, ch.name, ch.id):
                raise Conflict(f"'{ch.name}' already exists under the target", code="NAME_TAKEN")
        for ch in children:
            ch.parent_id = tgt.id
            ch.path_ids, ch.path_names, ch.depth = [*tgt.path_ids, ch.id], f"{tgt.path_names} › {ch.name}", tgt.depth + 1
            self._repath_descendants(ch, [x for x in subtree if ch.id in x.path_ids])
        src.archived_at = datetime.now(UTC)
        await self._finish()
        return CategoryMergeOut(moved_activities=moved_activities, moved_allocations=moved_alloc, preview=False)
