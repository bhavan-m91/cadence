"""Tags are overlay labels (D-02): many per activity, may overlap, may carry a weekly goal (FR-091..FR-104)."""

import hashlib
import re
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import rolls_back_on_error
from app.core.errors import AppError, Conflict, NotFound, ValidationFailed
from app.core.time import get_zone, week_start_date
from app.models import ActivityTag, Category, KeywordRule, Tag, TagAlias, User
from app.models.enums import GoalKind, KeywordTarget
from app.repositories.activities import ActivitiesRepository, ActivityFilters
from app.repositories.taxonomy import TaxonomyRepository
from app.repositories.users import UsersRepository
from app.schemas.activity import ActivityOut
from app.schemas.taxonomy import (
    AliasesIn,
    KeywordRuleCreate,
    KeywordRuleOut,
    TagCreate,
    TagMergeOut,
    TagOut,
    TagPatch,
)
from app.services import serializers
from app.services.category_service import PALETTE

ALIAS_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _:-]{0,47}$")


def goal_status(tag: Tag, minutes: int) -> str:
    if tag.goal_kind == GoalKind.tracked or tag.goal_weekly_minutes is None:
        return "none"
    if tag.goal_kind == GoalKind.max:
        return "over" if minutes > tag.goal_weekly_minutes else "ok"
    return "met" if minutes >= tag.goal_weekly_minutes else "under"


def auto_color(name: str) -> str:
    return PALETTE[int(hashlib.sha1(name.encode()).hexdigest(), 16) % len(PALETTE)]


class TagService:
    def __init__(self, session: AsyncSession, user: User):
        self.session, self.user = session, user
        self.repo = TaxonomyRepository(session, user.id)

    async def _get(self, tag_id: uuid.UUID, *, for_update: bool = False) -> Tag:
        t = await self.repo.tag(tag_id, for_update=for_update)
        if t is None:
            raise NotFound("Tag not found")
        return t

    async def _finish(self) -> None:
        try:
            await self.session.flush()
            await UsersRepository(self.session).bump_revision(self.user.id)
            await self.session.commit()
        except IntegrityError as e:
            await self.session.rollback()
            msg = str(e.orig)
            if "tags_user_name_uq" in msg or "tag_aliases_user_alias_uq" in msg:
                raise Conflict("That name is already in use", code="NAME_TAKEN") from e
            if "keyword_rules_uq" in msg:
                raise Conflict("That rule already exists", code="RULE_EXISTS") from e
            raise

    async def _week_range(self, from_date=None, to_date=None):
        if from_date and to_date:
            return from_date, to_date
        prefs = await UsersRepository(self.session).preferences(self.user.id)
        today = datetime.now(UTC).astimezone(get_zone(self.user.timezone)).date()
        start = week_start_date(today, prefs.week_start)
        return from_date or start, to_date or start + timedelta(days=6)

    def _validate_goal(self, kind: GoalKind, minutes: int | None) -> int | None:
        if kind == GoalKind.tracked:
            return None
        if not minutes:
            raise ValidationFailed("A weekly goal needs minutes", path="goal_weekly_minutes", rule="required")
        return minutes

    async def _check_name_free(self, name: str, exclude: uuid.UUID | None = None) -> None:
        existing = await self.repo.tag_by_name(name)
        if existing and existing.id != exclude:
            raise Conflict("A tag with that name exists", code="NAME_TAKEN")
        alias = await self.repo.alias_owner(name)
        if alias and alias.tag_id != exclude:
            raise Conflict("That name is an alias of another tag", code="NAME_TAKEN")

    async def _out(self, tags: list[Tag], f, t) -> list[TagOut]:
        minutes = await self.repo.tag_minutes(f, t, [x.id for x in tags])
        aliases = await self.repo.aliases_for([x.id for x in tags])
        out = []
        for tag in tags:
            o = TagOut.model_validate(tag)
            o.archived = tag.archived_at is not None
            o.aliases = aliases.get(tag.id, [])
            o.minutes_in_range = minutes.get(tag.id, 0)
            o.goal_status = goal_status(tag, o.minutes_in_range)
            out.append(o)
        return out

    # ---- tags
    async def list_tags(self, archived: bool, q: str | None, from_date, to_date) -> list[TagOut]:
        f, t = await self._week_range(from_date, to_date)
        return await self._out(await self.repo.tags(archived, q), f, t)

    @rolls_back_on_error
    async def create(self, body: TagCreate) -> TagOut:
        await self._check_name_free(body.name)
        minutes = self._validate_goal(body.goal_kind, body.goal_weekly_minutes)
        tag = Tag(user_id=self.user.id, name=body.name, color=body.color or auto_color(body.name), description=body.description,
                  goal_kind=body.goal_kind, goal_weekly_minutes=minutes)
        self.session.add(tag)
        await self._finish()
        f, t = await self._week_range()
        return (await self._out([tag], f, t))[0]

    async def detail(self, tag_id: uuid.UUID, from_date, to_date) -> dict:
        tag = await self._get(tag_id)
        f, t = await self._week_range(from_date, to_date)
        base = (await self._out([tag], f, t))[0]
        by_day = await self.repo.tag_minutes_by_day(tag.id, f, t)
        days = [{"date": (f + timedelta(days=i)).isoformat(), "minutes": by_day.get(f + timedelta(days=i), 0)} for i in range((t - f).days + 1)]
        acts, _ = await self._recent(tag.id)
        rules = [r.phrase for r in await self.repo.rules(KeywordTarget.tag, tag.id)]
        return {**base.model_dump(), "by_day": days, "recent_activities": acts, "total_minutes": base.minutes_in_range, "keywords": rules}

    async def _recent(self, tag_id: uuid.UUID) -> tuple[list[ActivityOut], bool]:
        repo = ActivitiesRepository(self.session, self.user.id)
        rows = await repo.search(ActivityFilters(tag_ids=[tag_id]), 10, None)
        return await serializers.activities_out(self.session, self.user.id, rows[:10]), len(rows) > 10

    @rolls_back_on_error
    async def patch(self, tag_id: uuid.UUID, body: TagPatch) -> TagOut:
        tag = await self._get(tag_id, for_update=True)
        if body.name is not None and body.name != tag.name:
            await self._check_name_free(body.name, tag.id)
            if body.keep_old_name_as_alias:
                self.session.add(TagAlias(user_id=self.user.id, tag_id=tag.id, alias=tag.name))
            tag.name = body.name
        if body.color is not None:
            tag.color = body.color
        if "description" in body.model_fields_set:
            tag.description = body.description
        if body.goal_kind is not None or "goal_weekly_minutes" in body.model_fields_set:
            kind = body.goal_kind or tag.goal_kind
            tag.goal_weekly_minutes = self._validate_goal(kind, body.goal_weekly_minutes if "goal_weekly_minutes" in body.model_fields_set else tag.goal_weekly_minutes)
            tag.goal_kind = kind
        if body.archived is not None:
            tag.archived_at = datetime.now(UTC) if body.archived else None
        await self._finish()
        f, t = await self._week_range()
        return (await self._out([tag], f, t))[0]

    @rolls_back_on_error
    async def delete(self, tag_id: uuid.UUID) -> None:
        tag = await self._get(tag_id, for_update=True)
        if await self.repo.tag_in_use(tag.id):
            raise Conflict("This tag is used by activities", code="TAG_IN_USE")
        await self.session.delete(tag)
        await self._finish()

    @rolls_back_on_error
    async def merge(self, source_id: uuid.UUID, target_id: uuid.UUID, preview: bool) -> TagMergeOut:
        src = await self._get(source_id, for_update=True)
        tgt = await self._get(target_id, for_update=True)
        if src.id == tgt.id or tgt.archived_at is not None or tgt.merged_into_id is not None:
            raise AppError("Choose a different, active target tag", code="INVALID_MERGE_TARGET", status=422)
        links = list((await self.session.execute(select(ActivityTag).where(ActivityTag.tag_id == src.id))).scalars())
        target_activity_ids = {
            a for (a,) in (await self.session.execute(select(ActivityTag.activity_id).where(ActivityTag.tag_id == tgt.id))).all()
        }
        dedup = [l for l in links if l.activity_id in target_activity_ids]
        moved = [l for l in links if l.activity_id not in target_activity_ids]
        if preview:
            return TagMergeOut(moved_links=len(moved), deduplicated=len(dedup), preview=True)

        for l in dedup:
            await self.session.delete(l)
        for l in moved:
            l.tag_id = tgt.id
        for alias in (await self.session.execute(select(TagAlias).where(TagAlias.tag_id == src.id))).scalars():
            alias.tag_id = tgt.id
        for rule in (await self.session.execute(select(KeywordRule).where(KeywordRule.tag_id == src.id))).scalars():
            dup = (await self.session.execute(select(KeywordRule).where(
                KeywordRule.user_id == self.user.id, KeywordRule.phrase == rule.phrase, KeywordRule.tag_id == tgt.id))).scalar_one_or_none()
            if dup:
                await self.session.delete(rule)
            else:
                rule.tag_id = tgt.id
        if tgt.goal_kind == GoalKind.tracked and src.goal_kind != GoalKind.tracked:
            tgt.goal_kind, tgt.goal_weekly_minutes = src.goal_kind, src.goal_weekly_minutes
        await self.session.flush()
        if not await self.repo.alias_owner(src.name):
            self.session.add(TagAlias(user_id=self.user.id, tag_id=tgt.id, alias=src.name))
        src.archived_at = datetime.now(UTC)
        src.merged_into_id = tgt.id
        await self._finish()
        return TagMergeOut(moved_links=len(moved), deduplicated=len(dedup), preview=False)

    @rolls_back_on_error
    async def put_aliases(self, tag_id: uuid.UUID, body: AliasesIn) -> list[str]:
        tag = await self._get(tag_id, for_update=True)
        cleaned: list[str] = []
        for a in body.aliases:
            if not ALIAS_RE.match(a):
                raise ValidationFailed(f"Invalid alias '{a}'", path="aliases", rule="invalid_alias")
            if a.lower() in {c.lower() for c in cleaned}:
                continue
            other = await self.repo.alias_owner(a)
            if other and other.tag_id != tag.id:
                raise Conflict(f"'{a}' is already an alias of another tag", code="ALIAS_TAKEN")
            clash = await self.repo.tag_by_name(a.lower())
            if clash and clash.merged_into_id is None:
                raise Conflict(f"'{a}' is the name of a tag", code="ALIAS_TAKEN")
            cleaned.append(a)
        await self.repo.replace_aliases(tag.id, cleaned)
        await self._finish()
        return cleaned

    # ---- keyword rules
    async def list_rules(self, target_type, target_id) -> list[KeywordRuleOut]:
        rules = await self.repo.rules(target_type, target_id)
        names: dict[uuid.UUID, str] = {}
        for r in rules:
            tid = r.tag_id or r.category_id
            if tid not in names:
                obj = await self.repo.get(Tag if r.tag_id else Category, tid)
                names[tid] = obj.name if obj else None
        return [KeywordRuleOut(id=r.id, phrase=r.phrase, target_type=r.target_type, target_id=r.tag_id or r.category_id,
                               target_name=names.get(r.tag_id or r.category_id)) for r in rules]

    @rolls_back_on_error
    async def create_rule(self, body: KeywordRuleCreate) -> KeywordRuleOut:
        phrase = body.phrase.lower()
        if body.target_type == KeywordTarget.tag:
            target = await self.repo.tag(body.target_id)
        else:
            target = await self.repo.category(body.target_id)
        if target is None:
            raise ValidationFailed("Unknown target", path="target_id", rule="not_found")
        rule = KeywordRule(user_id=self.user.id, phrase=phrase, target_type=body.target_type,
                           tag_id=body.target_id if body.target_type == KeywordTarget.tag else None,
                           category_id=body.target_id if body.target_type == KeywordTarget.category else None)
        self.session.add(rule)
        await self._finish()
        return KeywordRuleOut(id=rule.id, phrase=rule.phrase, target_type=rule.target_type, target_id=body.target_id, target_name=target.name)

    @rolls_back_on_error
    async def delete_rule(self, rule_id: uuid.UUID) -> None:
        rule = await self.repo.get(KeywordRule, rule_id)
        if rule is None:
            raise NotFound("Rule not found")
        await self.session.delete(rule)
        await self.session.commit()
