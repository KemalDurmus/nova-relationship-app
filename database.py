import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Render'ın gizli kasasından şifreli linki çeker. Bulamazsa geçici olarak SQLite kullanır.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./nova_database.db")

# PostgreSQL ve SQLite motorlarının çalışma prensipleri farklıdır, buna göre ayırıyoruz:
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()