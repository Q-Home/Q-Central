from sqlmodel import SQLModel, Session, create_engine
from .config import get_settings

settings = get_settings()

if settings.database_url:
    engine = create_engine(settings.database_url, pool_pre_ping=True)
else:
    engine = create_engine(f"sqlite:///{settings.db_path}", connect_args={"check_same_thread": False})


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session
