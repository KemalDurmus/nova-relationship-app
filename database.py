import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

# .env dosyasını oku
load_dotenv()

# .env içinde geçerli bir PostgreSQL adresi yoksa, doğrudan SQLite'a (nova_database.db) geç!
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///nova_database.db")

# Bulut (Render vb.) uyumluluğu için postgres:// düzeltmesi
if SQLALCHEMY_DATABASE_URL and SQLALCHEMY_DATABASE_URL.startswith("postgres://"):
    SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Eğer veritabanı SQLite ise özel bir ayar (check_same_thread) gerekiyor, PostgreSQL ise normal bağlanıyor.
if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(SQLALCHEMY_DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()