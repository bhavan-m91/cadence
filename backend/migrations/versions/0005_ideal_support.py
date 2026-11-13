"""ideal templates, export jobs, idempotency keys

Revision ID: 0005
Revises: 0004
"""
from app.core.migration_utils import run

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run([
        """CREATE TABLE ideal_templates (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            kind ideal_kind NOT NULL,
            effective_from date NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ideal_templates_uq UNIQUE (user_id, kind, effective_from)
        )""",
        "CREATE INDEX ideal_templates_lookup_idx ON ideal_templates (user_id, kind, effective_from DESC)",
        """CREATE TABLE ideal_allocations (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            template_id uuid NOT NULL REFERENCES ideal_templates(id) ON DELETE CASCADE,
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            category_id uuid NOT NULL REFERENCES categories(id) ON DELETE RESTRICT,
            minutes integer NOT NULL CHECK (minutes > 0 AND minutes % 5 = 0 AND minutes <= 10080),
            distribution ideal_distribution NOT NULL DEFAULT 'all_days',
            CONSTRAINT ideal_allocations_uq UNIQUE (template_id, category_id)
        )""",
        "CREATE INDEX ideal_allocations_category_idx ON ideal_allocations (category_id)",
        """CREATE TABLE export_jobs (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            status export_status NOT NULL DEFAULT 'queued',
            file_key text,
            size_bytes bigint,
            expires_at timestamptz,
            error_code varchar(40),
            created_at timestamptz NOT NULL DEFAULT now(),
            finished_at timestamptz
        )""",
        "CREATE INDEX export_jobs_user_idx ON export_jobs (user_id, created_at DESC)",
        """CREATE TABLE idempotency_keys (
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            key varchar(64) NOT NULL,
            endpoint varchar(100) NOT NULL,
            request_hash char(64) NOT NULL,
            response_status smallint NOT NULL,
            response_body jsonb NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (user_id, key, endpoint)
        )""",
    ])


def downgrade() -> None:
    run([f"DROP TABLE IF EXISTS {t} CASCADE" for t in ("idempotency_keys", "export_jobs", "ideal_allocations", "ideal_templates")])
