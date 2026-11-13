"""extensions, enum types and the updated_at trigger function

Revision ID: 0001
Revises:
"""
from app.core.migration_utils import run

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

ENUMS = {
    "theme_pref": ["system", "light", "dark"],
    "time_format": ["12h", "24h"],
    "coverage_preset": ["whole_day", "last_hours", "since_last", "custom"],
    "transcription_mode": ["auto", "server_only", "browser_only"],
    "email_token_purpose": ["verify_email", "reset_password"],
    "auth_event_type": ["login_ok", "login_fail", "logout", "password_changed", "reset_requested", "reset_done", "google_linked"],
    "input_method": ["typed", "dictated"],
    "entry_status": ["draft", "processing", "review", "confirmed", "failed", "manual"],
    "ai_job_type": ["extract_activities"],
    "ai_job_status": ["queued", "running", "succeeded", "failed", "cancelled"],
    "task_status": ["open", "done", "dropped"],
    "root_kind": ["work", "personal", "sleep"],
    "goal_kind": ["tracked", "min", "max"],
    "activity_status": ["draft", "confirmed"],
    "activity_kind": ["actual", "planned"],
    "location_type": ["office", "home", "remote", "travel", "other"],
    "placement": ["placed", "unplaced"],
    "time_certainty": ["stated", "inferred", "estimated"],
    "activity_origin": ["ai", "manual", "split", "merge", "duplicate"],
    "tag_source": ["ai", "rule", "alias", "user"],
    "activity_event_type": ["created", "edited", "tagged", "untagged", "task_linked", "split", "merged", "duplicated", "approved", "deleted", "restored"],
    "event_actor": ["user", "ai", "system"],
    "ideal_kind": ["day", "week"],
    "ideal_distribution": ["all_days", "weekdays", "weekend"],
    "export_status": ["queued", "running", "succeeded", "failed", "expired"],
    "keyword_target": ["tag", "category"],
}


def upgrade() -> None:
    stmts = [f"CREATE EXTENSION IF NOT EXISTS {e}" for e in ("btree_gist", "pg_trgm", "citext", "pgcrypto")]
    for name, values in ENUMS.items():
        labels = ", ".join(f"'{v}'" for v in values)
        stmts.append(f"CREATE TYPE {name} AS ENUM ({labels})")
    stmts.append(
        "CREATE FUNCTION set_updated_at() RETURNS trigger LANGUAGE plpgsql AS $$ "
        "BEGIN NEW.updated_at = now(); RETURN NEW; END; $$"
    )
    run(stmts)


def downgrade() -> None:
    stmts = ["DROP FUNCTION IF EXISTS set_updated_at()"]
    stmts += [f"DROP TYPE IF EXISTS {name}" for name in reversed(list(ENUMS))]
    run(stmts)
