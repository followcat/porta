from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.exceptions import AuthenticationError, ValidationError
from app.core.security import hash_password, verify_password
from app.db.models.user import User
from app.repositories.user_repo import UserRepository
from app.services.audit_service import AuditService


class AuthService:
    def __init__(self, session: Session):
        self.session = session
        self.users = UserRepository(session)
        self.audit = AuditService(session)

    def authenticate(self, username: str, password: str) -> User:
        user = self.users.get_by_username(username)
        if not user or not user.is_active or not verify_password(password, user.password_hash):
            raise AuthenticationError("invalid username or password")
        self.audit.log(user.id, "login_success", "user", str(user.id), {"username": user.username})
        return user

    def create_admin(self, username: str, password: str) -> User:
        if self.users.get_by_username(username):
            raise ValidationError("username already exists")
        user = User(username=username, password_hash=hash_password(password), role="admin", is_active=True)
        self.users.create(user)
        self.audit.log(user.id, "admin_created", "user", str(user.id), {"username": user.username})
        return user
