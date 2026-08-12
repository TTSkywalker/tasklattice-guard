from __future__ import annotations

from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope


class ControlPlaneStaticFiles(StaticFiles):
    """Serve the SPA entry point for current control-plane route namespaces."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except HTTPException as error:
            if (
                error.status_code != 404
                or not _accepts_html(scope)
                or path.split("/", 1)[0]
                not in {
                    "dashboard",
                    "guardrails",
                    "control-library",
                    "playground",
                    "evaluations",
                    "deployments",
                    "assignments",
                    "enforcements",
                    "integrations",
                    "evidence",
                    "access",
                }
            ):
                raise
            return await super().get_response("index.html", scope)


def _accepts_html(scope: Scope) -> bool:
    return any(
        name.lower() == b"accept" and b"text/html" in value.lower()
        for name, value in scope.get("headers", [])
    )
