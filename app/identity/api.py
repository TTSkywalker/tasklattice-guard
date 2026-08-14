from __future__ import annotations

from dataclasses import asdict
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from .service import (
    IdentityAuthenticationError,
    IdentityAuthorizationError,
    IdentityError,
    IdentityService,
    IdentityUser,
)


SESSION_COOKIE = "tasklattice_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 7


class CreateUserRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=10, max_length=256)
    preferred_language: Literal["en", "zh-CN"] = "en"
    role: Literal["admin", "member"] = "member"


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class UpdateUserRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    role: Literal["admin", "member"] | None = None
    enabled: bool | None = None
    password: str | None = Field(default=None, min_length=10, max_length=256)


class UpdateMeRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    preferred_language: Literal["en", "zh-CN"] | None = None


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=10, max_length=256)


class IdentityAPI:
    def __init__(self, service: IdentityService) -> None:
        self._service = service
        self.router = APIRouter(prefix="/api/v1", tags=["identity"])
        self._register_routes()

    def require_user(self, request: Request) -> IdentityUser:
        try:
            return self._service.authenticate(request.cookies.get(SESSION_COOKIE))
        except IdentityAuthenticationError as error:
            raise HTTPException(status_code=401, detail=str(error)) from error

    def require_admin(self, request: Request) -> IdentityUser:
        user = self.require_user(request)
        if user.role != "admin":
            raise HTTPException(status_code=403, detail="Administrator access is required.")
        return user

    def _register_routes(self) -> None:
        @self.router.get("/session")
        def status(request: Request):
            try:
                user = self._service.authenticate(request.cookies.get(SESSION_COOKIE))
            except IdentityAuthenticationError:
                user = None
            return {
                "authenticated": user is not None,
                "user": _user_payload(user) if user else None,
            }

        @self.router.post("/session")
        def login(request: LoginRequest, response: Response, http_request: Request):
            try:
                result = self._service.login(email=request.email, password=request.password)
            except IdentityError as error:
                _raise_identity(error)
            _set_session_cookie(response, http_request, result.session_token)
            return {"user": _user_payload(result.user)}

        @self.router.delete("/session", status_code=204)
        def logout(request: Request, response: Response):
            self._service.logout(request.cookies.get(SESSION_COOKIE))
            response.delete_cookie(SESSION_COOKIE, path="/", samesite="lax")
            return None

        @self.router.patch("/me")
        def update_me(request: UpdateMeRequest, http_request: Request):
            user = self.require_user(http_request)
            try:
                updated = self._service.update_profile(
                    user.id,
                    display_name=request.display_name,
                    preferred_language=request.preferred_language,
                )
            except IdentityError as error:
                _raise_identity(error)
            return {"user": _user_payload(updated)}

        @self.router.patch("/me/password")
        def change_password(request: ChangePasswordRequest, http_request: Request):
            user = self.require_user(http_request)
            try:
                updated = self._service.change_password(
                    user.id,
                    current_password=request.current_password,
                    new_password=request.new_password,
                    current_session_token=http_request.cookies.get(SESSION_COOKIE) or "",
                )
            except IdentityError as error:
                _raise_identity(error)
            return {"user": _user_payload(updated)}

        @self.router.get("/users")
        def users(http_request: Request):
            self.require_admin(http_request)
            return {"users": [_user_payload(item) for item in self._service.users()]}

        @self.router.post("/users", status_code=201)
        def create_user(request: CreateUserRequest, http_request: Request):
            self.require_admin(http_request)
            try:
                user = self._service.create_user(
                    display_name=request.display_name,
                    email=request.email,
                    password=request.password,
                    role=request.role,
                    preferred_language=request.preferred_language,
                )
            except IdentityError as error:
                _raise_identity(error)
            return _user_payload(user)

        @self.router.patch("/users/{user_id}")
        def update_user(
            user_id: str, request: UpdateUserRequest, http_request: Request
        ):
            actor = self.require_admin(http_request)
            try:
                user = self._service.update_user(
                    user_id,
                    actor_id=actor.id,
                    display_name=request.display_name,
                    role=request.role,
                    enabled=request.enabled,
                    password=request.password,
                )
            except IdentityError as error:
                _raise_identity(error)
            return _user_payload(user)


def _user_payload(user: IdentityUser) -> dict[str, object]:
    return asdict(user)


def _set_session_cookie(response: Response, request: Request, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
        path="/",
    )


def _raise_identity(error: IdentityError) -> None:
    if isinstance(error, IdentityAuthenticationError):
        raise HTTPException(status_code=401, detail=str(error)) from error
    if isinstance(error, IdentityAuthorizationError):
        raise HTTPException(status_code=403, detail=str(error)) from error
    raise HTTPException(status_code=400, detail=str(error)) from error
