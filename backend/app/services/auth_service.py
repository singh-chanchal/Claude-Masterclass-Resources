from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import User
from app.security import hash_password, verify_password
from app.services.errors import BadRequest


def signup(db: Session, name: str, email: str, password: str) -> User:
    email = email.strip().lower()
    if db.scalar(select(User).where(func.lower(User.email) == email)):
        raise BadRequest("An account with this email already exists.")
    user = User(name=name.strip(), email=email, password_hash=hash_password(password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate(db: Session, email: str, password: str) -> User | None:
    user = db.scalar(select(User).where(func.lower(User.email) == email.strip().lower()))
    if user and verify_password(password, user.password_hash):
        return user
    return None


def change_password(db: Session, user: User, current_password: str, new_password: str) -> None:
    # 400, not 401: a 401 makes the frontend log the user out.
    if not verify_password(current_password, user.password_hash):
        raise BadRequest("Current password is incorrect.")
    user.password_hash = hash_password(new_password)
    db.commit()
