"""User authentication and initial account provisioning."""
from sqlalchemy import or_
from sqlalchemy.orm import Session
from werkzeug.security import check_password_hash, generate_password_hash

from app.models.database import User
from app.schemas.user import UserCreate


class UserService:
    def __init__(self, db: Session):
        self.db = db

    def authenticate(self, login: str, password: str) -> User | None:
        normalized = login.strip().lower()
        user = self.db.query(User).filter(
            or_(User.username == normalized, User.email == normalized)
        ).first()
        if not user or not user.is_active:
            return None
        return user if check_password_hash(user.hashed_password, password) else None

    def seed_initial_users(self, user_data: list[UserCreate]) -> list[User]:
        if self.db.query(User).count() > 0:
            raise ValueError("Users already exist; initial user seeding is disabled")

        usernames = [item.username.strip().lower() for item in user_data]
        emails = [item.email.strip().lower() for item in user_data]
        if len(usernames) != len(set(usernames)):
            raise ValueError("Each username must be unique")
        if len(emails) != len(set(emails)):
            raise ValueError("Each email address must be unique")

        users = [
            User(
                username=item.username.strip().lower(),
                email=item.email.strip().lower(),
                full_name=item.full_name.strip(),
                role=item.role.strip().lower(),
                department=item.department.strip() if item.department else None,
                hashed_password=generate_password_hash(item.password),
                is_active=item.is_active,
            )
            for item in user_data
        ]
        self.db.add_all(users)
        self.db.commit()
        for user in users:
            self.db.refresh(user)
        return users
