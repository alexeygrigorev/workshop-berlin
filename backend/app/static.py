"""Optional static frontend serving (single-origin deployments, e.g. the Docker image).

Enabled by WSWE_STATIC_DIR (a built SPA directory containing index.html). Installed after the API routers, so
/v1/* routes always win; unknown /v1/* paths stay 404 JSON-ish instead of falling back to the SPA shell.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response

IMMUTABLE = "public, max-age=31536000, immutable"
NO_CACHE = "no-cache"
SHORT = "public, max-age=3600"


def install_static(app: FastAPI, static_dir: str | Path) -> None:
    root = Path(static_dir).resolve()
    index = root / "index.html"
    if not index.is_file():
        raise RuntimeError(f"WSWE_STATIC_DIR={static_dir!s} has no index.html")

    def serve_index() -> Response:
        return FileResponse(index, media_type="text/html", headers={"Cache-Control": NO_CACHE})

    @app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    async def spa(path: str) -> Response:
        if path == "v1" or path.startswith("v1/"):
            raise HTTPException(404, "Not found")
        if path in ("", "index.html"):
            return serve_index()
        try:
            target = (root / path).resolve()
            target.relative_to(root)  # blocks ../ and symlink escapes
        except (ValueError, OSError):
            raise HTTPException(404, "Not found")
        if target.is_file():
            hashed = path.startswith("assets/")  # Vite emits content-hashed files under assets/
            return FileResponse(target, headers={"Cache-Control": IMMUTABLE if hashed else SHORT})
        # Missing asset or other file-looking path: a real 404, not HTML. Anything else is a client-side route.
        if path.startswith("assets/") or "." in path.rsplit("/", 1)[-1]:
            raise HTTPException(404, "Not found")
        return serve_index()
