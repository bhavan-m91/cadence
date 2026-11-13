import uuid
from typing import Any, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

M = TypeVar("M")


class UserScopedRepository:
    """Every query adds `user_id` (tenant isolation by construction, PRD 9.3). Soft-deleted rows are invisible."""

    def __init__(self, session: AsyncSession, user_id: uuid.UUID):
        self.session = session
        self.user_id = user_id

    async def get(self, model: type[M], id: uuid.UUID, *, for_update: bool = False) -> M | None:
        stmt = select(model).where(model.id == id, model.user_id == self.user_id)  # type: ignore[attr-defined]
        if hasattr(model, "deleted_at"):
            stmt = stmt.where(model.deleted_at.is_(None))  # type: ignore[attr-defined]
        if for_update:
            stmt = stmt.with_for_update()
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_many(self, model: type[M], ids: list[uuid.UUID]) -> list[M]:
        if not ids:
            return []
        stmt = select(model).where(model.id.in_(ids), model.user_id == self.user_id)  # type: ignore[attr-defined]
        if hasattr(model, "deleted_at"):
            stmt = stmt.where(model.deleted_at.is_(None))  # type: ignore[attr-defined]
        return list((await self.session.execute(stmt)).scalars())

    def add(self, obj: Any) -> Any:
        self.session.add(obj)
        return obj
