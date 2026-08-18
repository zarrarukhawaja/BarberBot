"""
This file sets up our database connection.
We're using SQLite: a database that's just a single file (barberbot.db),
no server to install or configure. Perfect for building and learning.
When we eventually have real customers, we can swap this for something
bigger (like Postgres) without rewriting the rest of the app.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = "sqlite:///./barberbot.db"

# check_same_thread=False is an SQLite-specific quirk needed when a web
# server (which handles multiple requests) talks to the same db file.
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """
    FastAPI will call this for every request that needs the database.
    The 'yield' pattern guarantees the connection closes properly even
    if something goes wrong mid-request.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
