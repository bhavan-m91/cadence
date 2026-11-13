from fastapi import APIRouter

from app.api.v1 import (
    activities,
    auth,
    categories,
    exports,
    health,
    ideal,
    journal,
    keyword_rules,
    projects,
    review,
    tags,
    tasks,
    timeline,
    users,
)

api_router = APIRouter(prefix="/api/v1")
for r in (health.router, auth.router, users.router, exports.router, activities.router, timeline.router, tasks.router,
          projects.router, categories.router, tags.router, keyword_rules.router, ideal.router, journal.router, review.router):
    api_router.include_router(r)
