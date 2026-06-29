"""Core data models for ArchaeoCode."""
from sqlalchemy import (
    Column, Integer, String, DateTime, Float, ForeignKey, create_engine
)
from sqlalchemy.orm import declarative_base, relationship, Session

Base = declarative_base()


class Commit(Base):
    __tablename__ = "commits"

    id = Column(Integer, primary_key=True)
    sha = Column(String, unique=True, index=True)
    author_name = Column(String, index=True)
    author_email = Column(String, index=True)
    message = Column(String)
    committed_date = Column(DateTime, index=True)
    insertions = Column(Integer, default=0)
    deletions = Column(Integer, default=0)
    files_changed_count = Column(Integer, default=0)

    file_changes = relationship("FileChange", back_populates="commit")


class FileChange(Base):
    __tablename__ = "file_changes"

    id = Column(Integer, primary_key=True)
    commit_id = Column(Integer, ForeignKey("commits.id"), index=True)
    file_path = Column(String, index=True)
    change_type = Column(String)   # 'A' added, 'M' modified, 'D' deleted, 'R' renamed
    insertions = Column(Integer, default=0)
    deletions = Column(Integer, default=0)

    commit = relationship("Commit", back_populates="file_changes")


def get_engine(db_path: str = "archaeocode.db"):
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    return engine


def get_session(engine) -> Session:
    return Session(engine)