from dataclasses import dataclass
from sqlalchemy.sql import func
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


@dataclass
class User(db.Model):
    """
    WordGame does not store password or token
    """
    user_id: str
    provider: str

    # OAuth2 sub(ject)
    user_id = db.Column(db.String(25), primary_key=True, nullable=False)
    # OAuth2 provider
    provider = db.Column(db.String(25), default='GOOGLE')


@dataclass
class Session(db.Model):
    id: str
    cursor: str

    STATUS_PLAYING = 1
    STATUS_DONE = 2

    id = db.Column(db.String(36), primary_key=True)
    user_id = db.Column(db.String(25))
    game_type = db.Column(db.String, nullable=False, default='gender')
    cursor = db.Column(db.String, nullable=False)
    status = db.Column(db.Integer, nullable=False, default=STATUS_PLAYING)
    created_at = db.Column(db.DateTime, default=func.now())


@dataclass
class Category(db.Model):
    """
    Category of the word
    """
    id: int
    name: str

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False, name="category_name")
    is_disabled = db.Column(db.Boolean, nullable=False, default=False)


@dataclass
class Collection(db.Model):
    id: int
    name: str

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    owner_id = db.Column(db.String(25), nullable=False)
    term_ids = db.Column(db.JSON)


@dataclass
class Term(db.Model):
    """
    Dictionary entries
    """
    id: int
    word: str
    tags: str

    id = db.Column(db.Integer, primary_key=True)
    word = db.Column(db.String(80), nullable=False)
    tags = db.Column(db.String(80), nullable=False)


class TermStat(db.Model):
    """
    Term Stat per user
    """
    __tablename__ = 'term_stat'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    week = db.Column(db.Integer, nullable=False, comment='Numerical presentation of week since epoch')
    session_id = db.Column(db.String(36))
    term_id = db.Column(db.Integer, nullable=False)
    corrects = db.Column(db.Integer, nullable=False, default=0)
    wrongs = db.Column(db.Integer, nullable=False, default=0)
    skippeds = db.Column(db.Integer, nullable=False, default=0)
    seconds = db.Column(db.Integer, nullable=False, default=0, comment='Seconds taken to respond to this term')
    seconds_correct = db.Column(db.Integer, nullable=True, comment='Seconds taken to correctly answer this term')


class WeeklyTermStat(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    week = db.Column(db.Integer, nullable=False, comment='Numerical presentation of week since epoch')
    session_id = db.Column(db.String(36))
    term_id = db.Column(db.Integer, nullable=False)
    corrects = db.Column(db.Integer, nullable=False, default=0)
    wrongs = db.Column(db.Integer, nullable=False, default=0)
    skippeds = db.Column(db.Integer, nullable=False, default=0)

    word = db.Column(db.VARCHAR(80), nullable=False)
    tags = db.Column(db.VARCHAR(80), nullable=False)