from sqlalchemy.orm import Session
from app.models.user import User


def get_by_username(db: Session, username: str) -> User | None:
    return db.query(User).filter(User.username == username).first()


def get_by_username_or_email(db: Session, username: str, email: str) -> User | None:
    return db.query(User).filter(
        (User.username == username) | (User.email == email)
    ).first()


def create_user(db: Session, username: str, email: str, hashed_password: str) -> User:
    user = User(username=username, email=email, hashed_password=hashed_password)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user