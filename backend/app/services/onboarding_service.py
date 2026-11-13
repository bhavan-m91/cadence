"""First-run seeding (FR-085, M-03): timezone, suggested taxonomy, example tags and rules, an Ideal Day preset."""

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import rolls_back_on_error
from app.core.errors import Conflict
from app.core.time import get_zone
from app.models import Category, IdealAllocation, IdealTemplate, KeywordRule, Tag, User
from app.models.enums import GoalKind, IdealDistribution, IdealKind, KeywordTarget, RootKind
from app.repositories.taxonomy import TaxonomyRepository
from app.repositories.users import UsersRepository
from app.schemas.user import OnboardingIn, OnboardingOut
from app.services.category_service import PALETTE, ensure_roots
from app.services.tag_service import auto_color

# (name, focus, is_transition)
WORK_CHILDREN = [("Deep work", True, False), ("Meetings", False, False), ("Sales & clients", True, False), ("Admin", False, False), ("Learning", True, False)]
PERSONAL_CHILDREN = [("Health", False, False), ("Family & friends", False, False), ("Meals & chores", False, False), ("Commute", False, False),
                     ("Entertainment", False, False), ("Transitions", False, True)]

EXAMPLE_TAGS = [("research", GoalKind.tracked, None), ("meetings", GoalKind.tracked, None), ("bug", GoalKind.tracked, None),
                ("p0", GoalKind.tracked, None), ("p1", GoalKind.tracked, None), ("social-media", GoalKind.max, 300)]
# phrase -> ("tag" | "category", name)
EXAMPLE_RULES = [("standup", "tag", "meetings"), ("debugging", "tag", "bug"), ("instagram", "tag", "social-media"),
                 ("youtube", "tag", "social-media"), ("lunch", "category", "Meals & chores"), ("commute", "category", "Commute"),
                 ("gym", "category", "Health")]

# A day that adds up to exactly 24h (1,440 min)
BALANCED_DAY = {"Sleep": 450, "Deep work": 270, "Meetings": 60, "Admin": 60, "Learning": 60, "Health": 60, "Family & friends": 150,
                "Meals & chores": 120, "Commute": 60, "Entertainment": 90, "Transitions": 60}


class OnboardingService:
    def __init__(self, session: AsyncSession, user: User):
        self.session, self.user = session, user
        self.repo = TaxonomyRepository(session, user.id)

    @rolls_back_on_error
    async def run(self, body: OnboardingIn) -> OnboardingOut:
        if self.user.onboarding_completed_at is not None:
            raise Conflict("Onboarding is already done", code="ALREADY_ONBOARDED")
        get_zone(body.timezone)
        self.user.timezone = body.timezone
        roots = await ensure_roots(self.session, self.user.id)
        created_cats: dict[str, Category] = {}
        tag_count = 0
        if body.seed == "default":
            existing_names = {c.name.lower() for c in await self.repo.categories(True)}
            i = 0
            for root_kind, children in ((RootKind.work, WORK_CHILDREN), (RootKind.personal, PERSONAL_CHILDREN)):
                parent = roots[root_kind]
                for order, (name, focus, transition) in enumerate(children):
                    if name.lower() in existing_names:
                        continue
                    cat = Category(
                        user_id=self.user.id, parent_id=parent.id, root_kind=root_kind, depth=2, name=name, path_ids=[],
                        path_names=f"{parent.path_names} › {name}", color=PALETTE[i % len(PALETTE)], counts_as_focus=focus,
                        is_transition=transition, sort_order=order,
                    )
                    self.session.add(cat)
                    await self.session.flush()
                    cat.path_ids = [*parent.path_ids, cat.id]
                    created_cats[name] = cat
                    i += 1
            tags: dict[str, Tag] = {}
            for name, kind, minutes in EXAMPLE_TAGS:
                if await self.repo.tag_by_name(name):
                    continue
                tag = Tag(user_id=self.user.id, name=name, color=auto_color(name), goal_kind=kind, goal_weekly_minutes=minutes)
                self.session.add(tag)
                tags[name] = tag
                tag_count += 1
            await self.session.flush()
            for phrase, target, name in EXAMPLE_RULES:
                if target == "tag" and name in tags:
                    self.session.add(KeywordRule(user_id=self.user.id, phrase=phrase, target_type=KeywordTarget.tag, tag_id=tags[name].id))
                elif target == "category" and name in created_cats:
                    self.session.add(KeywordRule(user_id=self.user.id, phrase=phrase, target_type=KeywordTarget.category, category_id=created_cats[name].id))
            if body.ideal_day_preset == "balanced":
                await self._seed_ideal_day({**created_cats, "Sleep": roots[RootKind.sleep]})
        self.user.onboarding_completed_at = datetime.now(UTC)
        await UsersRepository(self.session).bump_revision(self.user.id)
        await self.session.commit()
        return OnboardingOut(categories_created=len(created_cats), tags_created=tag_count)

    async def _seed_ideal_day(self, cats: dict[str, Category]) -> None:
        if any(name not in cats for name in BALANCED_DAY):
            return
        today = datetime.now(UTC).astimezone(get_zone(self.user.timezone)).date()
        tpl = IdealTemplate(user_id=self.user.id, kind=IdealKind.day, effective_from=today)
        self.session.add(tpl)
        await self.session.flush()
        assert sum(BALANCED_DAY.values()) == 1440
        for name, minutes in BALANCED_DAY.items():
            self.session.add(IdealAllocation(template_id=tpl.id, user_id=self.user.id, category_id=cats[name].id, minutes=minutes,
                                             distribution=IdealDistribution.all_days))
