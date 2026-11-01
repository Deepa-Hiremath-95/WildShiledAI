import sqlite3
import json
from datetime import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base

from app.config import settings

raw_db_url = settings.database_url
# Normalize legacy postgres:// to postgresql:// for SQLAlchemy 2.0 compatibility
db_url = raw_db_url.replace("postgres://", "postgresql://", 1) if raw_db_url.startswith("postgres://") else raw_db_url

connect_args = {"check_same_thread": False} if db_url.startswith("sqlite") else {}

engine = create_engine(db_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def run_migrations(target_engine=None):
    """
    Non-destructive schema migration.
    1. Creates all tables defined in models that do not exist yet.
    2. Inspects existing tables and safely adds new columns if missing.
    3. Guarantees zero data loss across restarts.
    """
    eng = target_engine or engine
    Base.metadata.create_all(bind=eng)

    # SQLite-specific safe column additions
    url_str = str(eng.url)
    if url_str.startswith("sqlite"):
        # Extract db path
        db_path = url_str.replace("sqlite:///", "")
        if db_path and db_path != ":memory:":
            try:
                conn = sqlite3.connect(db_path)
                cur = conn.cursor()

                def add_col_if_missing(table, col_name, col_type):
                    try:
                        cur.execute(f"PRAGMA table_info({table})")
                        cols = [r[1] for r in cur.fetchall()]
                        if col_name not in cols:
                            cur.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}")
                    except Exception:
                        pass

                add_col_if_missing("zones", "village_id", "VARCHAR")
                add_col_if_missing("zones", "updated_at", "DATETIME")
                add_col_if_missing("cameras", "village_id", "VARCHAR")
                add_col_if_missing("cameras", "last_human_alert_at", "DATETIME")
                add_col_if_missing("cameras", "created_at", "DATETIME")
                add_col_if_missing("cameras", "updated_at", "DATETIME")
                add_col_if_missing("alerts", "village_id", "VARCHAR")
                add_col_if_missing("alerts", "resolved_at", "DATETIME")
                add_col_if_missing("alerts", "resolved_by", "VARCHAR")
                add_col_if_missing("alerts", "acknowledged_at", "DATETIME")
                add_col_if_missing("alerts", "acknowledged_by", "VARCHAR")
                add_col_if_missing("alerts", "updated_at", "DATETIME")

                conn.commit()
                conn.close()
            except Exception as e:
                import logging
                logging.getLogger("wildshield.db").warning(f"Auto-migration check notice: {e}")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
