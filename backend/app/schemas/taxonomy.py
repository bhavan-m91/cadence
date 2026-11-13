import re
import uuid

from pydantic import BaseModel, Field, field_validator

from app.models.enums import GoalKind, KeywordTarget, RootKind
from app.schemas.common import ORM, Color, Str

TAG_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*(:[a-z0-9][a-z0-9_-]*)?$")


class CategoryOut(ORM):
    id: uuid.UUID
    parent_id: uuid.UUID | None
    root_kind: RootKind
    depth: int
    name: str
    path_names: str
    color: str
    description: str | None
    counts_as_focus: bool
    is_system: bool
    is_transition: bool
    sort_order: int
    archived: bool = False


class CategoryNode(CategoryOut):
    children: list["CategoryNode"] = Field(default_factory=list)


class CategoryChip(ORM):
    id: uuid.UUID
    name: str
    path_names: str
    color: str
    root_kind: RootKind


class CategoryCreate(BaseModel):
    parent_id: uuid.UUID
    name: Str = Field(min_length=1, max_length=60)
    color: Color | None = None
    description: Str | None = Field(default=None, max_length=300)
    counts_as_focus: bool = False
    is_transition: bool = False


class CategoryPatch(BaseModel):
    name: Str | None = Field(default=None, min_length=1, max_length=60)
    color: Color | None = None
    description: Str | None = Field(default=None, max_length=300)
    counts_as_focus: bool | None = None
    is_transition: bool | None = None
    parent_id: uuid.UUID | None = None
    sort_order: int | None = None
    archived: bool | None = None


class MergeIn(BaseModel):
    target_id: uuid.UUID
    preview: bool = False


class CategoryMergeOut(BaseModel):
    moved_activities: int
    moved_allocations: int
    preview: bool


class TagMergeOut(BaseModel):
    moved_links: int
    deduplicated: int
    preview: bool


class TagChip(ORM):
    id: uuid.UUID
    name: str
    color: str


class TagOut(ORM):
    id: uuid.UUID
    name: str
    color: str
    description: str | None
    goal_kind: GoalKind
    goal_weekly_minutes: int | None
    archived: bool = False
    aliases: list[str] = Field(default_factory=list)
    minutes_in_range: int = 0
    goal_status: str = "none"


class TagCreate(BaseModel):
    name: Str = Field(min_length=1, max_length=48)
    color: Color | None = None
    description: Str | None = Field(default=None, max_length=300)
    goal_kind: GoalKind = GoalKind.tracked
    goal_weekly_minutes: int | None = Field(default=None, gt=0)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = v.lower().lstrip("#")
        if not TAG_NAME_RE.match(v):
            raise ValueError("Use lowercase letters, digits, - and _ (optional namespace: prefix)")
        return v


class TagPatch(BaseModel):
    name: Str | None = Field(default=None, min_length=1, max_length=48)
    color: Color | None = None
    description: Str | None = Field(default=None, max_length=300)
    goal_kind: GoalKind | None = None
    goal_weekly_minutes: int | None = Field(default=None, gt=0)
    archived: bool | None = None
    keep_old_name_as_alias: bool = False

    @field_validator("name")
    @classmethod
    def _name(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.lower().lstrip("#")
        if not TAG_NAME_RE.match(v):
            raise ValueError("Use lowercase letters, digits, - and _ (optional namespace: prefix)")
        return v


class AliasesIn(BaseModel):
    aliases: list[Str] = Field(max_length=30)


class KeywordRuleCreate(BaseModel):
    phrase: Str = Field(min_length=1, max_length=60)
    target_type: KeywordTarget
    target_id: uuid.UUID


class KeywordRuleOut(BaseModel):
    id: uuid.UUID
    phrase: str
    target_type: KeywordTarget
    target_id: uuid.UUID
    target_name: str | None = None
