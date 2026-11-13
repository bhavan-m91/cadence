"""Run raw DDL statements one by one (asyncpg cannot prepare multi-statement strings)."""

from alembic import op


def run(statements: list[str]) -> None:
    for stmt in statements:
        op.execute(stmt)


def updated_at_trigger(table: str) -> str:
    return (
        f"CREATE TRIGGER {table}_set_updated_at BEFORE UPDATE ON {table} "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
