from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path


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
    """Manage local users and opaque browser sessions in the control-plane DB."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        self._ensure_default_admin()

    def users(self) -> tuple[IdentityUser, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM users ORDER BY display_name COLLATE NOCASE, email"
            ).fetchall()
        return tuple(_user_from_row(row) for row in rows)

    def user(self, user_id: str) -> IdentityUser:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM users WHERE id = ?", (user_id,)
            ).fetchone()
        if row is None:
            raise IdentityValidationError("User was not found.")
        return _user_from_row(row)

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
        now = _now()
        user_id = f"user-{uuid.uuid4().hex[:12]}"
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO users
                        (id, display_name, email, role, password_salt, password_hash,
                         enabled, preferred_language, last_login_at, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, 1, ?, NULL, ?, ?)
                    """,
                    (
                        user_id,
                        name,
                        normalized_email,
                        role,
                        salt,
                        _password_hash(password, salt),
                        preferred_language,
                        now,
                        now,
                    ),
                )
                connection.commit()
        except sqlite3.IntegrityError as error:
            raise IdentityValidationError("A user with this email already exists.") from error
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
        current = self.user(user_id)
        next_name = current.display_name if display_name is None else display_name.strip()
        next_role = current.role if role is None else role
        next_enabled = current.enabled if enabled is None else enabled
        next_language = (
            current.preferred_language
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
        if current.role == "admin" and current.enabled and (
            next_role != "admin" or not next_enabled
        ):
            if self._enabled_admin_count() <= 1:
                raise IdentityValidationError("At least one enabled administrator is required.")

        deployments = [
            "display_name = ?",
            "role = ?",
            "enabled = ?",
            "preferred_language = ?",
            "updated_at = ?",
        ]
        values: list[object] = [
            next_name,
            next_role,
            int(next_enabled),
            next_language,
            _now(),
        ]
        if password is not None:
            salt = secrets.token_hex(16)
            deployments.extend(("password_salt = ?", "password_hash = ?"))
            values.extend((salt, _password_hash(password, salt)))
        values.append(user_id)
        with self._connect() as connection:
            connection.execute(
                f"UPDATE users SET {', '.join(deployments)} WHERE id = ?",
                tuple(values),
            )
            if not next_enabled or password is not None:
                connection.execute(
                    "DELETE FROM user_sessions WHERE user_id = ?", (user_id,)
                )
            connection.commit()
        return self.user(user_id)

    def update_preferred_language(
        self, user_id: str, preferred_language: str
    ) -> IdentityUser:
        _validate_language(preferred_language)
        with self._connect() as connection:
            connection.execute(
                "UPDATE users SET preferred_language = ?, updated_at = ? WHERE id = ?",
                (preferred_language, _now(), user_id),
            )
            connection.commit()
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
        with self._connect() as connection:
            row = connection.execute(
                "SELECT password_salt, password_hash FROM users WHERE id = ? AND enabled = 1",
                (user_id,),
            ).fetchone()
            if row is None or not hmac.compare_digest(
                str(row["password_hash"]),
                _password_hash(current_password, str(row["password_salt"])),
            ):
                raise IdentityValidationError("Current password is incorrect.")
            if hmac.compare_digest(
                str(row["password_hash"]),
                _password_hash(new_password, str(row["password_salt"])),
            ):
                raise IdentityValidationError(
                    "New password must be different from the current password."
                )

            salt = secrets.token_hex(16)
            connection.execute(
                """
                UPDATE users
                SET password_salt = ?, password_hash = ?, updated_at = ?
                WHERE id = ?
                """,
                (salt, _password_hash(new_password, salt), _now(), user_id),
            )
            connection.execute(
                "DELETE FROM user_sessions WHERE user_id = ? AND token_hash != ?",
                (user_id, _token_hash(current_session_token)),
            )
            connection.commit()
        return self.user(user_id)

    def login(self, *, email: str, password: str) -> LoginResult:
        normalized_email = _normalize_login_identifier(email)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM users WHERE email = ? COLLATE NOCASE",
                (normalized_email,),
            ).fetchone()
        if row is None or not bool(row["enabled"]):
            raise IdentityAuthenticationError("Email or password is incorrect.")
        expected = str(row["password_hash"])
        actual = _password_hash(password, str(row["password_salt"]))
        if not hmac.compare_digest(expected, actual):
            raise IdentityAuthenticationError("Email or password is incorrect.")

        token = secrets.token_urlsafe(36)
        now = datetime.now(UTC)
        expires = now + timedelta(days=SESSION_DAYS)
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM user_sessions WHERE expires_at <= ?", (now.isoformat(),)
            )
            connection.execute(
                """
                INSERT INTO user_sessions (token_hash, user_id, expires_at, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (_token_hash(token), str(row["id"]), expires.isoformat(), now.isoformat()),
            )
            connection.execute(
                "UPDATE users SET last_login_at = ?, updated_at = ? WHERE id = ?",
                (now.isoformat(), now.isoformat(), str(row["id"])),
            )
            connection.commit()
        return LoginResult(self.user(str(row["id"])), token)

    def authenticate(self, token: str | None) -> IdentityUser:
        if not token:
            raise IdentityAuthenticationError("Authentication is required.")
        now = _now()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT u.* FROM user_sessions s
                JOIN users u ON u.id = s.user_id
                WHERE s.token_hash = ? AND s.expires_at > ? AND u.enabled = 1
                """,
                (_token_hash(token), now),
            ).fetchone()
        if row is None:
            raise IdentityAuthenticationError("Your session has expired.")
        return _user_from_row(row)

    def logout(self, token: str | None) -> None:
        if not token:
            return
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM user_sessions WHERE token_hash = ?", (_token_hash(token),)
            )
            connection.commit()

    def _enabled_admin_count(self) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) FROM users WHERE role = 'admin' AND enabled = 1"
            ).fetchone()
        return int(row[0]) if row else 0

    def _ensure_default_admin(self) -> None:
        """Create the built-in local administrator only for an empty user store."""
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT COUNT(*) FROM users").fetchone()
            if row and int(row[0]) > 0:
                connection.commit()
                return
            salt = secrets.token_hex(16)
            now = _now()
            connection.execute(
                """
                INSERT INTO users
                    (id, display_name, email, role, password_salt, password_hash,
                     enabled, preferred_language, last_login_at, created_at, updated_at)
                VALUES (?, ?, ?, 'admin', ?, ?, 1, 'en', NULL, ?, ?)
                """,
                (
                    DEFAULT_ADMIN_ID,
                    DEFAULT_ADMIN_NAME,
                    DEFAULT_ADMIN_EMAIL,
                    salt,
                    _password_hash(DEFAULT_ADMIN_PASSWORD, salt),
                    now,
                    now,
                ),
            )
            connection.commit()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection


def _user_from_row(row: sqlite3.Row) -> IdentityUser:
    return IdentityUser(
        id=str(row["id"]),
        display_name=str(row["display_name"]),
        email=str(row["email"]),
        role=str(row["role"]),
        enabled=bool(row["enabled"]),
        preferred_language=str(row["preferred_language"]),
        last_login_at=str(row["last_login_at"]) if row["last_login_at"] else None,
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
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
        raise IdentityValidationError("Display name is required and must be under 120 characters.")


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


def _now() -> str:
    return datetime.now(UTC).isoformat()
