"""journal, AI jobs and activities: entries, revisions, jobs, activities, tags, day slices, events

Revision ID: 0004
Revises: 0003
"""
from app.core.migration_utils import run, updated_at_trigger

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run([
        """CREATE TABLE journal_entries (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            entry_date date NOT NULL,
            covers_start_at timestamptz NOT NULL,
            covers_end_at timestamptz NOT NULL,
            timezone varchar(64) NOT NULL,
            raw_text text NOT NULL CHECK (char_length(raw_text) BETWEEN 1 AND 10000),
            text_hash char(64) NOT NULL,
            title varchar(120),
            input_method input_method NOT NULL DEFAULT 'typed',
            dictation_seconds integer,
            status entry_status NOT NULL DEFAULT 'draft',
            latest_job_id uuid,
            revision integer NOT NULL DEFAULT 1,
            version integer NOT NULL DEFAULT 1,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            deleted_at timestamptz,
            CONSTRAINT journal_window_chk CHECK (covers_end_at > covers_start_at AND covers_end_at - covers_start_at <= interval '24 hours')
        )""",
        "CREATE INDEX journal_entries_date_idx ON journal_entries (user_id, entry_date DESC)",
        "CREATE INDEX journal_entries_status_idx ON journal_entries (user_id, status)",
        "CREATE INDEX journal_entries_text_trgm ON journal_entries USING gin (raw_text gin_trgm_ops)",
        """CREATE TABLE journal_entry_revisions (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            entry_id uuid NOT NULL REFERENCES journal_entries(id) ON DELETE CASCADE,
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            revision integer NOT NULL,
            raw_text text NOT NULL,
            covers_start_at timestamptz NOT NULL,
            covers_end_at timestamptz NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT journal_revisions_uq UNIQUE (entry_id, revision)
        )""",
        """CREATE FUNCTION reject_modification() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'DELETE' AND pg_trigger_depth() > 1 THEN RETURN OLD; END IF;
            RAISE EXCEPTION '% is append-only', TG_TABLE_NAME;
        END; $$""",
        "CREATE TRIGGER journal_revisions_append_only BEFORE UPDATE OR DELETE ON journal_entry_revisions FOR EACH ROW EXECUTE FUNCTION reject_modification()",
        """CREATE TABLE ai_processing_jobs (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            entry_id uuid NOT NULL REFERENCES journal_entries(id),
            job_type ai_job_type NOT NULL DEFAULT 'extract_activities',
            status ai_job_status NOT NULL DEFAULT 'queued',
            attempts smallint NOT NULL DEFAULT 0 CHECK (attempts <= 3),
            entry_revision integer NOT NULL,
            text_hash char(64) NOT NULL,
            user_hint varchar(500),
            prompt_version varchar(32) NOT NULL,
            provider varchar(32) NOT NULL,
            model varchar(64) NOT NULL,
            raw_response jsonb,
            parsed_response jsonb,
            input_tokens integer,
            output_tokens integer,
            latency_ms integer,
            error_code varchar(40),
            is_stale boolean NOT NULL DEFAULT false,
            created_at timestamptz NOT NULL DEFAULT now(),
            queued_at timestamptz,
            started_at timestamptz,
            finished_at timestamptz
        )""",
        "CREATE INDEX ai_jobs_entry_idx ON ai_processing_jobs (entry_id, created_at DESC)",
        "CREATE INDEX ai_jobs_active_idx ON ai_processing_jobs (status, queued_at) WHERE status IN ('queued', 'running')",
        "CREATE INDEX ai_jobs_user_idx ON ai_processing_jobs (user_id, created_at)",
        "ALTER TABLE journal_entries ADD CONSTRAINT journal_entries_latest_job_fk FOREIGN KEY (latest_job_id) REFERENCES ai_processing_jobs(id)",
        """CREATE TABLE activities (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            journal_entry_id uuid REFERENCES journal_entries(id) ON DELETE SET NULL,
            source_job_id uuid REFERENCES ai_processing_jobs(id) ON DELETE SET NULL,
            status activity_status NOT NULL DEFAULT 'confirmed',
            kind activity_kind NOT NULL DEFAULT 'actual',
            title varchar(120) NOT NULL,
            description text CHECK (char_length(description) <= 2000),
            category_id uuid NOT NULL REFERENCES categories(id) ON DELETE RESTRICT,
            task_id uuid REFERENCES tasks(id) ON DELETE SET NULL,
            project_id uuid REFERENCES projects(id) ON DELETE SET NULL,
            location_type location_type,
            placement placement NOT NULL,
            start_at timestamptz,
            end_at timestamptz,
            window_start_at timestamptz,
            window_end_at timestamptz,
            duration_minutes integer,
            time_certainty time_certainty NOT NULL DEFAULT 'stated',
            timezone varchar(64) NOT NULL,
            local_date date NOT NULL,
            origin activity_origin NOT NULL DEFAULT 'manual',
            confidence numeric(3,2) CHECK (confidence BETWEEN 0 AND 1),
            needs_review boolean NOT NULL DEFAULT false,
            flags text[] NOT NULL DEFAULT '{}',
            source_quote text,
            source_start integer,
            source_end integer,
            source_revision integer,
            ai_proposed jsonb,
            user_edited boolean NOT NULL DEFAULT false,
            derived_from_id uuid REFERENCES activities(id),
            merged_into_id uuid REFERENCES activities(id),
            version integer NOT NULL DEFAULT 1,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            deleted_at timestamptz,
            CONSTRAINT activities_time_chk CHECK (
                (placement = 'placed' AND start_at IS NOT NULL AND end_at > start_at
                    AND duration_minutes::numeric = EXTRACT(EPOCH FROM (end_at - start_at)) / 60)
                OR (placement = 'unplaced' AND start_at IS NULL AND window_start_at IS NOT NULL AND window_end_at > window_start_at)),
            CONSTRAINT activities_duration_chk CHECK (status = 'draft' OR duration_minutes BETWEEN 1 AND 1440)
        )""",
        """ALTER TABLE activities ADD CONSTRAINT activities_no_overlap
            EXCLUDE USING gist (user_id WITH =, tstzrange(start_at, end_at, '[)') WITH &&)
            WHERE (status = 'confirmed' AND kind = 'actual' AND placement = 'placed' AND deleted_at IS NULL)""",
        "CREATE INDEX activities_user_date_idx ON activities (user_id, local_date)",
        "CREATE INDEX activities_user_start_idx ON activities (user_id, start_at)",
        "CREATE INDEX activities_user_category_idx ON activities (user_id, category_id)",
        "CREATE INDEX activities_entry_idx ON activities (journal_entry_id)",
        "CREATE INDEX activities_task_idx ON activities (task_id)",
        "CREATE INDEX activities_draft_idx ON activities (user_id) WHERE status = 'draft'",
        "CREATE INDEX activities_title_trgm ON activities USING gin (title gin_trgm_ops)",
        """CREATE TABLE activity_tags (
            activity_id uuid NOT NULL REFERENCES activities(id) ON DELETE CASCADE,
            tag_id uuid NOT NULL REFERENCES tags(id) ON DELETE RESTRICT,
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            source tag_source NOT NULL,
            confidence numeric(3,2),
            reason varchar(160),
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (activity_id, tag_id)
        )""",
        "CREATE INDEX activity_tags_tag_idx ON activity_tags (tag_id, activity_id)",
        "CREATE INDEX activity_tags_user_tag_idx ON activity_tags (user_id, tag_id)",
        """CREATE TABLE activity_day_slices (
            activity_id uuid NOT NULL REFERENCES activities(id) ON DELETE CASCADE,
            local_date date NOT NULL,
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            minutes smallint NOT NULL CHECK (minutes BETWEEN 1 AND 1500),
            is_placed boolean NOT NULL,
            slice_start_at timestamptz,
            slice_end_at timestamptz,
            category_id uuid NOT NULL,
            time_certainty time_certainty NOT NULL,
            location_type location_type,
            PRIMARY KEY (activity_id, local_date)
        )""",
        "CREATE INDEX slices_user_date_idx ON activity_day_slices (user_id, local_date)",
        "CREATE INDEX slices_user_category_date_idx ON activity_day_slices (user_id, category_id, local_date)",
        """CREATE TABLE activity_events (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            activity_id uuid NOT NULL REFERENCES activities(id),
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            event_type activity_event_type NOT NULL,
            actor event_actor NOT NULL,
            payload jsonb,
            created_at timestamptz NOT NULL DEFAULT clock_timestamp()
        )""",
        "CREATE INDEX activity_events_activity_idx ON activity_events (activity_id, created_at)",
        updated_at_trigger("journal_entries"),
        updated_at_trigger("activities"),
    ])


def downgrade() -> None:
    run([
        "ALTER TABLE journal_entries DROP CONSTRAINT IF EXISTS journal_entries_latest_job_fk",
        *[f"DROP TABLE IF EXISTS {t} CASCADE" for t in (
            "activity_events", "activity_day_slices", "activity_tags", "activities", "ai_processing_jobs",
            "journal_entry_revisions", "journal_entries")],
        "DROP FUNCTION IF EXISTS reject_modification()",
    ])
