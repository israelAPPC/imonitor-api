import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

load_dotenv()

# Usa DATABASE_URL se existir, senão cai pro SQLite
# Lembre-se de colocar a Connection String no Render e no arquivo .env local
# IMPORTANTE: Se a senha tiver '@', tem que colocar '%40' no lugar, senão dá erro!
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./licenses.db")

# Corrige postgres:// para postgresql:// para compatibilidade com SQLAlchemy 2.0
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
