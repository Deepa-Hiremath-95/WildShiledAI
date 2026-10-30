from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.config import settings

raw_db_url = settings.database_url
# Normalize legacy postgres:// to postgresql:// for SQLAlchemy 2.0 compatibility
db_url = raw_db_url.replace("postgres://", "postgresql://", 1) if raw_db_url.startswith("postgres://") else raw_db_url

connect_args = {"check_same_thread": False} if db_url.startswith("sqlite") else {}

engine = create_engine(db_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
