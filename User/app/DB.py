# loja/User/app/DB.py

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
# CORREÇÃO: Importar a classe Session
from sqlalchemy.orm import Session, sessionmaker
from .settings import Settings

engine = create_engine(Settings().DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_session():
    # AGORA Session está definido, pois foi importado acima
    with Session(engine) as session:
        yield session

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()