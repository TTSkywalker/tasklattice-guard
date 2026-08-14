from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from ..persistence import Database, DatabaseLocator
from ..persistence.models import UserModel, UserSessionModel

SESSION_DAYS = 7
PASSWORD_ITERATIONS = 310_000
DEFAULT_ADMIN_ID = "user-default-admin"
DEFAULT_ADMIN_NAME = "Administrator"
DEFAULT_ADMIN_EMAIL = "admin@tasklattice.local"
DEFAULT_ADMIN_PASSWORD = "admin"


class IdentityError(RuntimeError):
    pass


class IdentityValidationError(IdentityError):
    pass


class IdentityAuthenticationError(IdentityError):
    pass


class IdentityAuthorizationError(IdentityError):
    pass


@dataclass(frozen=True, slots=True)
class IdentityUser:
    id: str
    display_name: str
    email: str
    role: str
    enabled: bool
    preferred_language: str
    last_login_at: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class LoginResult:
    user: IdentityUser
    session_token: str


class IdentityService:
    """Manage local users and opaque browser sessions through SQLAlchemy."""

    def __init__(self, database: Database | DatabaseLocator) -> None:
        self._database = database if isinstance(database, Database) else Database(database)
        self._database.create_schema()
        self._ensure_default_admin()

    def users(self) -> tuple[IdentityUser, ...]:
        with self._database.session() as session:
            rows = session.scalars(
                select(UserModel).order_by(
                    func.lower(UserModel.display_name), UserModel.email
                )
            ).all()
            return tuple(_user_from_model(row) for row in rows)

    def user(self, user_id: str) -> IdentityUser:
        with self._database.session() as session:
            row = session.get(UserModel, user_id)
            if row is None:
                raise IdentityValidationError("User was not found.")
            return _user_from_model(row)

    def create_user(
        self,
        *,
        display_name: str,
        email: str,
        password: str,
        role: str,
        preferred_language: str = "en",
    ) -> IdentityUser:
        name = display_name.strip()
        normalized_email = _normalize_email(email)
        _validate_name(name)
        _validate_password(password)
        _validate_role(role)
        _validate_language(preferred_language)
        salt = secrets.token_hex(16)
        now = _utcnow()
        user_id = f"user-{uuid.uuid4().hex[:12]}"
        try:
            with self._database.transaction() as session:
                session.add(
                    UserModel(
                        id=user_id,
                        display_name=name,
                        email=normalized_email,
                        role=role,
                        password_salt=salt,
                        password_hash=_password_hash(password, salt),
                        enabled=True,
                        preferred_language=preferred_language,
                        last_login_at=None,
                        created_at=now,
                        updated_at=now,
                    )
                )
        except IntegrityError as error:
            raise IdentityValidationError(
                "A user with this email already exists."
            ) from error
        return self.user(user_id)

    def update_user(
        self,
        user_id: str,
        *,
        actor_id: str,
        display_name: str | None = None,
        role: str | None = None,
        enabled: bool | None = None,
        password: str | None = None,
        preferred_language: str | None = None,
    ) -> IdentityUser:
        with self._database.transaction() as session:
            row = session.scalar(
                select(UserModel)
                .where(UserModel.id == user_id)
                .with_for_update()
            )
            if row is None:
                raise IdentityValidationError("User was not found.")
            next_name = row.display_name if display_name is None else display_name.strip()
            next_role = row.role if role is None else role
            next_enabled = row.enabled if enabled is None else enabled
            next_language = (
                row.preferred_language
                if preferred_language is None
                else preferred_language
            )
            _validate_name(next_name)
            _validate_role(next_role)
            _validate_language(next_language)
            if password is not None:
                _validate_password(password)
            if user_id == actor_id and not next_enabled:
                raise IdentityValidationError("You cannot disable your own account.")
            if row.role == "admin" and row.enabled and (
                next_role != "admin" or not next_enabled
            ):
                enabled_admins = session.scalar(
                    select(func.count())
                    .select_from(UserModel)
                    .where(UserModel.role == "admin", UserModel.enabled.is_(True))
                )
                if int(enabled_admins or 0) <= 1:
                    raise IdentityValidationError(
                        "At least one enabled administrator is required."
                    )
            row.display_name = next_name
            row.role = next_role
            row.enabled = next_enabled
            row.preferred_language = next_language
            row.updated_at = _utcnow()
            if password is not None:
                salt = secrets.token_hex(16)
                row.password_salt = salt
                row.password_hash = _password_hash(password, salt)
            if not next_enabled or password is not None:
                session.execute(
                    delete(UserSessionModel).where(UserSessionModel.user_id == user_id)
                )
        return self.user(user_id)

    def update_preferred_language(
        self, user_id: str, preferred_language: str
    ) -> IdentityUser:
        return self.update_profile(
            user_id,
            preferred_language=preferred_language,
        )

    def update_profile(
        self,
        user_id: str,
        *,
        display_name: str | None = None,
        preferred_language: str | None = None,
    ) -> IdentityUser:
        with self._database.transaction() as session:
            row = session.get(UserModel, user_id)
            if row is None:
                raise IdentityValidationError("User was not found.")
            next_name = row.display_name if display_name is None else display_name.strip()
            next_language = (
                row.preferred_language
                if preferred_language is None
                else preferred_language
            )
            _validate_name(next_name)
            _validate_language(next_language)
            row.display_name = next_name
            row.preferred_language = next_language
            row.updated_at = _utcnow()
        return self.user(user_id)

    def change_password(
        self,
        user_id: str,
        *,
        current_password: str,
        new_password: str,
        current_session_token: str,
    ) -> IdentityUser:
        _validate_password(new_password)
        with self._database.transaction() as session:
            row = session.scalar(
                select(UserModel)
                .where(UserModel.id == user_id, UserModel.enabled.is_(True))
                .with_for_update()
            )
            if row is None or not hmac.compare_digest(
                row.password_hash,
                _password_hash(current_password, row.password_salt),
            ):
                raise IdentityValidationError("Current password is incorrect.")
            if hmac.compare_digest(
                row.password_hash,
                _password_hash(new_password, row.password_salt),
            ):
                raise IdentityValidationError(
                    "New password must be different from the current password."
                )
            salt = secrets.token_hex(16)
            row.password_salt = salt
            row.password_hash = _password_hash(new_password, salt)
            row.updated_at = _utcnow()
            session.execute(
                delete(UserSessionModel).where(
                    UserSessionModel.user_id == user_id,
                    UserSessionModel.token_hash != _token_hash(current_session_token),
                )
            )
        return self.user(user_id)

    def login(self, *, email: str, password: str) -> LoginResult:
        normalized_email = _normalize_login_identifier(email)
        with self._database.session() as session:
            row = session.scalar(
                select(UserModel).where(
                    func.lower(UserModel.email) == normalized_email
                )
            )
            if row is None or not row.enabled:
                raise IdentityAuthenticationError("Email or password is incorrect.")
            user_id = row.id
            expected = row.password_hash
            actual = _password_hash(password, row.password_salt)
        if not hmac.compare_digest(expected, actual):
            raise IdentityAuthenticationError("Email or password is incorrect.")

        token = secrets.token_urlsafe(36)
        now = _utcnow()
        with self._database.transaction() as session:
            session.execute(
                delete(UserSessionModel).where(UserSessionModel.expires_at <= now)
            )
            session.add(
                UserSessionModel(
                    token_hash=_token_hash(token),
                    user_id=user_id,
                    expires_at=now + timedelta(days=SESSION_DAYS),
                    created_at=now,
                )
            )
            user = session.get(UserModel, user_id)
            assert user is not None
            user.last_login_at = now
            user.updated_at = now
        return LoginResult(self.user(user_id), token)

    def authenticate(self, token: str | None) -> IdentityUser:
        if not token:
            raise IdentityAuthenticationError("Authentication is required.")
        with self._database.session() as session:
            row = session.scalar(
                select(UserModel)
                .join(UserSessionModel, UserSessionModel.user_id == UserModel.id)
                .where(
                    UserSessionModel.token_hash == _token_hash(token),
                    UserSessionModel.expires_at > _utcnow(),
                    UserModel.enabled.is_(True),
                )
            )
            if row is None:
                raise IdentityAuthenticationError("Your session has expired.")
            return _user_from_model(row)

    def logout(self, token: str | None) -> None:
        if not token:
            return
        with self._database.transaction() as session:
            session.execute(
                delete(UserSessionModel).where(
                    UserSessionModel.token_hash == _token_hash(token)
                )
            )

    def _ensure_default_admin(self) -> None:
        """Create the built-in local administrator only for an empty user store."""
        try:
            with self._database.transaction() as session:
                existing = session.scalar(
                    select(UserModel.id).limit(1).with_for_update()
                )
                if existing is not None:
                    return
                salt = secrets.token_hex(16)
                now = _utcnow()
                session.add(
                    UserModel(
                        id=DEFAULT_ADMIN_ID,
                        display_name=DEFAULT_ADMIN_NAME,
                        email=DEFAULT_ADMIN_EMAIL,
                        role="admin",
                        password_salt=salt,
                        password_hash=_password_hash(DEFAULT_ADMIN_PASSWORD, salt),
                        enabled=True,
                        preferred_language="en",
                        last_login_at=None,
                        created_at=now,
                        updated_at=now,
                    )
                )
        except IntegrityError as error:
            # Two application replicas may race on the first boot. The database
            # uniqueness constraints make the default identity idempotent.
            with self._database.session() as session:
                if session.get(UserModel, DEFAULT_ADMIN_ID) is None:
                    raise IdentityError(
                        "The default administrator could not be initialized."
                    ) from error


def _user_from_model(row: UserModel) -> IdentityUser:
    return IdentityUser(
        id=row.id,
        display_name=row.display_name,
        email=row.email,
        role=row.role,
        enabled=row.enabled,
        preferred_language=row.preferred_language,
        last_login_at=_iso(row.last_login_at),
        created_at=_iso(row.created_at) or "",
        updated_at=_iso(row.updated_at) or "",
    )


def _password_hash(password: str, salt: str) -> str:
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode(),
        bytes.fromhex(salt),
        PASSWORD_ITERATIONS,
    )
    return digest.hex()


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _normalize_email(value: str) -> str:
    email = value.strip().casefold()
    if "@" not in email or email.startswith("@") or email.endswith("@"):
        raise IdentityValidationError("Enter a valid work email address.")
    return email


def _normalize_login_identifier(value: str) -> str:
    identifier = value.strip().casefold()
    if "@" in identifier:
        return _normalize_email(identifier)
    if not identifier or len(identifier) > 64 or not all(
        character.isalnum() or character in {"-", "_", "."}
        for character in identifier
    ):
        raise IdentityAuthenticationError(
            "Email, username, or password is incorrect."
        )
    return f"{identifier}@tasklattice.local"


def _validate_name(value: str) -> None:
    if not value or len(value) > 120:
        raise IdentityValidationError(
            "Display name is required and must be under 120 characters."
        )


def _validate_password(value: str) -> None:
    if len(value) < 10:
        raise IdentityValidationError("Password must contain at least 10 characters.")
    if len(value) > 256:
        raise IdentityValidationError("Password is too long.")


def _validate_role(value: str) -> None:
    if value not in {"admin", "member"}:
        raise IdentityValidationError("Unsupported user role.")


def _validate_language(value: str) -> None:
    if value not in {"en", "zh-CN"}:
        raise IdentityValidationError("Unsupported language.")


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    normalized = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return normalized.isoformat()
