"""One-shot additive schema ensure for Postgres/SQLite (missing observation columns)."""
from __future__ import annotations
import os
from sqlalchemy import create_engine, inspect, text

def run(database_url: str | None = None) -> list[str]:
    url = database_url or os.getenv("DATABASE_URL", "sqlite:///./nexgene.db")
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    eng = create_engine(url)
    done: list[str] = []
    insp = inspect(eng)
    tables = set(insp.get_table_names())
    is_sqlite = url.startswith("sqlite")

    def add_col(table: str, col: str, ddl: str) -> None:
        if table not in tables:
            return
        cols = {c["name"] for c in insp.get_columns(table)}
        if col in cols:
            return
        with eng.begin() as conn:
            conn.execute(text(ddl))
        done.append(f"{table}.{col}")

    obs_at = "DATETIME" if is_sqlite else "TIMESTAMPTZ"
    add_col("observations", "data_domain", "ALTER TABLE observations ADD COLUMN data_domain VARCHAR(40) DEFAULT 'lifestyle'")
    add_col("observations", "source_type", "ALTER TABLE observations ADD COLUMN source_type VARCHAR(40) DEFAULT 'user-entered'")
    add_col("observations", "unit", "ALTER TABLE observations ADD COLUMN unit VARCHAR(40)")
    add_col("observations", "quality_flag", "ALTER TABLE observations ADD COLUMN quality_flag VARCHAR(32) DEFAULT 'self_reported'")
    add_col("observations", "observed_at", f"ALTER TABLE observations ADD COLUMN observed_at {obs_at}")
    add_col("observations", "supersedes_id", "ALTER TABLE observations ADD COLUMN supersedes_id INTEGER")
    add_col("observations", "period", "ALTER TABLE observations ADD COLUMN period VARCHAR(24)")
    add_col("profiles", "location_city", "ALTER TABLE profiles ADD COLUMN location_city VARCHAR(160)")
    if is_sqlite:
        add_col("profiles", "live_context_enabled", "ALTER TABLE profiles ADD COLUMN live_context_enabled BOOLEAN DEFAULT 1")
        add_col("users", "email_verified", "ALTER TABLE users ADD COLUMN email_verified BOOLEAN DEFAULT 0")
        add_col("users", "ai_analysis_enabled", "ALTER TABLE users ADD COLUMN ai_analysis_enabled BOOLEAN DEFAULT 0")
    else:
        add_col("profiles", "live_context_enabled", "ALTER TABLE profiles ADD COLUMN live_context_enabled BOOLEAN DEFAULT TRUE")
        add_col("users", "email_verified", "ALTER TABLE users ADD COLUMN email_verified BOOLEAN DEFAULT FALSE")
        add_col("users", "ai_analysis_enabled", "ALTER TABLE users ADD COLUMN ai_analysis_enabled BOOLEAN DEFAULT FALSE")
    add_col("users", "google_sub", "ALTER TABLE users ADD COLUMN google_sub VARCHAR(255)")
    return done

if __name__ == "__main__":
    print(run())
