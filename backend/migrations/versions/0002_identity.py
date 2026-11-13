"""identity: users, preferences, refresh tokens, email tokens, auth events

Revision ID: 0002
Revises: 0001
"""
from app.core.migration_utils import run, updated_at_trigger

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run([
        """CREATE TABLE users (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            email citext NOT NULL UNIQUE,
            email_verified_at timestamptz,
            password_hash text,
            google_sub text UNIQUE,
            display_name varchar(80) NOT NULL CHECK (char_length(display_name) >= 1),
            role_title varchar(80),
            timezone varchar(64) NOT NULL DEFAULT 'Asia/Kolkata',
            theme theme_pref NOT NULL DEFAULT 'system',
            data_revision bigint NOT NULL DEFAULT 0,
            onboarding_completed_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT users_credential_chk CHECK (password_hash IS NOT NULL OR google_sub IS NOT NULL)
        )""",
        """CREATE TABLE user_preferences (
            user_id uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            week_start smallint NOT NULL DEFAULT 1 CHECK (week_start BETWEEN 1 AND 7),
            time_format time_format NOT NULL DEFAULT '12h',
            coverage_tolerance_minutes smallint NOT NULL DEFAULT 10 CHECK (coverage_tolerance_minutes BETWEEN 0 AND 60),
            gap_min_minutes smallint NOT NULL DEFAULT 10 CHECK (gap_min_minutes BETWEEN 1 AND 60),
            short_night_minutes smallint NOT NULL DEFAULT 420 CHECK (short_night_minutes BETWEEN 240 AND 600),
            office_start_minute smallint NOT NULL DEFAULT 540,
            office_end_minute smallint NOT NULL DEFAULT 1080,
            ai_enabled boolean NOT NULL DEFAULT true,
            default_coverage_preset coverage_preset NOT NULL DEFAULT 'whole_day',
            transcription_mode transcription_mode NOT NULL DEFAULT 'auto',
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT office_hours_chk CHECK (office_start_minute >= 0 AND office_end_minute <= 1440 AND office_start_minute < office_end_minute)
        )""",
        """CREATE TABLE refresh_tokens (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            family_id uuid NOT NULL,
            token_hash char(64) NOT NULL UNIQUE,
            created_at timestamptz NOT NULL DEFAULT now(),
            expires_at timestamptz NOT NULL,
            rotated_at timestamptz,
            revoked_at timestamptz,
            user_agent varchar(200),
            ip inet
        )""",
        "CREATE INDEX refresh_tokens_family_idx ON refresh_tokens (family_id)",
        "CREATE INDEX refresh_tokens_user_idx ON refresh_tokens (user_id)",
        """CREATE TABLE email_tokens (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            purpose email_token_purpose NOT NULL,
            token_hash char(64) NOT NULL UNIQUE,
            expires_at timestamptz NOT NULL,
            used_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now()
        )""",
        "CREATE INDEX email_tokens_user_idx ON email_tokens (user_id)",
        """CREATE TABLE auth_events (
            id bigserial PRIMARY KEY,
            user_id uuid REFERENCES users(id) ON DELETE CASCADE,
            event_type auth_event_type NOT NULL,
            ip inet,
            user_agent varchar(200),
            created_at timestamptz NOT NULL DEFAULT now()
        )""",
        "CREATE INDEX auth_events_user_idx ON auth_events (user_id, created_at DESC)",
        updated_at_trigger("users"),
        updated_at_trigger("user_preferences"),
    ])


def downgrade() -> None:
    run([f"DROP TABLE IF EXISTS {t} CASCADE" for t in ("auth_events", "email_tokens", "refresh_tokens", "user_preferences", "users")])
