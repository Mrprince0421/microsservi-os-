from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from .settings import Settings
from sqlalchemy.orm import sessionmaker

engine = create_engine(Settings().DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
def get_session():
    with Session(engine) as session:
        yield session

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()