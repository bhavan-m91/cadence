"""taxonomy and tasks: categories, tags, aliases, keyword rules, projects, tasks

Revision ID: 0003
Revises: 0002
"""
from app.core.migration_utils import run, updated_at_trigger

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run([
        """CREATE TABLE categories (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            parent_id uuid REFERENCES categories(id),
            root_kind root_kind NOT NULL,
            depth smallint NOT NULL CHECK (depth BETWEEN 1 AND 3),
            name varchar(60) NOT NULL,
            path_ids uuid[] NOT NULL,
            path_names text NOT NULL,
            color char(7) NOT NULL,
            description varchar(300),
            counts_as_focus boolean NOT NULL DEFAULT false,
            is_system boolean NOT NULL DEFAULT false,
            is_transition boolean NOT NULL DEFAULT false,
            sort_order integer NOT NULL DEFAULT 0,
            archived_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT categories_root_depth_chk CHECK ((parent_id IS NULL) = (depth = 1))
        )""",
        "CREATE UNIQUE INDEX categories_sibling_name_uq ON categories (user_id, COALESCE(parent_id, user_id), lower(name))",
        "CREATE INDEX categories_path_gin ON categories USING gin (path_ids)",
        "CREATE INDEX categories_user_idx ON categories (user_id)",
        """CREATE TABLE tags (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name varchar(48) NOT NULL CHECK (name ~ '^[a-z0-9][a-z0-9_-]*(:[a-z0-9][a-z0-9_-]*)?$'),
            color char(7) NOT NULL,
            description varchar(300),
            goal_kind goal_kind NOT NULL DEFAULT 'tracked',
            goal_weekly_minutes integer CHECK (goal_weekly_minutes > 0),
            archived_at timestamptz,
            merged_into_id uuid REFERENCES tags(id) ON DELETE SET NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT tags_user_name_uq UNIQUE (user_id, name),
            CONSTRAINT tags_goal_chk CHECK ((goal_kind = 'tracked') = (goal_weekly_minutes IS NULL))
        )""",
        """CREATE TABLE tag_aliases (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            tag_id uuid NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
            alias varchar(48) NOT NULL
        )""",
        "CREATE UNIQUE INDEX tag_aliases_user_alias_uq ON tag_aliases (user_id, lower(alias))",
        "CREATE INDEX tag_aliases_tag_idx ON tag_aliases (tag_id)",
        """CREATE TABLE keyword_rules (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            phrase varchar(60) NOT NULL,
            target_type keyword_target NOT NULL,
            tag_id uuid REFERENCES tags(id) ON DELETE CASCADE,
            category_id uuid REFERENCES categories(id) ON DELETE CASCADE,
            CONSTRAINT keyword_rules_target_chk CHECK (
                (target_type = 'tag' AND tag_id IS NOT NULL AND category_id IS NULL)
                OR (target_type = 'category' AND category_id IS NOT NULL AND tag_id IS NULL))
        )""",
        "CREATE UNIQUE INDEX keyword_rules_uq ON keyword_rules (user_id, phrase, target_type, COALESCE(tag_id, category_id))",
        """CREATE TABLE projects (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name varchar(80) NOT NULL,
            color char(7),
            archived_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )""",
        "CREATE UNIQUE INDEX projects_user_name_uq ON projects (user_id, lower(name))",
        """CREATE TABLE tasks (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            project_id uuid REFERENCES projects(id) ON DELETE SET NULL,
            title varchar(160) NOT NULL,
            description text CHECK (char_length(description) <= 4000),
            priority smallint CHECK (priority BETWEEN 0 AND 3),
            due_date date,
            status task_status NOT NULL DEFAULT 'open',
            estimate_minutes integer CHECK (estimate_minutes > 0),
            completed_at timestamptz,
            version integer NOT NULL DEFAULT 1,
            created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            deleted_at timestamptz
        )""",
        "CREATE INDEX tasks_user_status_due_idx ON tasks (user_id, status, due_date)",
        "CREATE INDEX tasks_title_trgm ON tasks USING gin (title gin_trgm_ops)",
        "CREATE INDEX tasks_project_idx ON tasks (project_id)",
        updated_at_trigger("categories"),
        updated_at_trigger("tags"),
        updated_at_trigger("projects"),
        updated_at_trigger("tasks"),
    ])


def downgrade() -> None:
    run([f"DROP TABLE IF EXISTS {t} CASCADE" for t in ("tasks", "projects", "keyword_rules", "tag_aliases", "tags", "categories")])
