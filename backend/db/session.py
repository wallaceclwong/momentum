"""
Database session configuration.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os

# SQLite database file path
DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "sqlite:///./data/momentum_screener.db"
)

# Create engine
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
