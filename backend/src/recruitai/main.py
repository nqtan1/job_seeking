import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Response
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.config import Settings
from recruitai.core.auth import warm_certs
from recruitai.core.db import close_db, get_db, init_db, warm_up
from recruitai.core.error_handlers import install_error_handlers
from recruitai.core.logging import configure_logging
from recruitai.core.middleware import RequestContextMiddleware
from recruitai.core.storage_routes import router as local_storage_router
from recruitai.core.tasks_routes import router as tasks_router
from recruitai.modules.applications.router import router as applications_router
from recruitai.modules.candidates.router import router as candidates_router
from recruitai.modules.coach.router import router as coach_router
from recruitai.modules.documents.router import router as documents_router
from recruitai.modules.documents.router import signature_router
from recruitai.modules.identity.router import admin_router
from recruitai.modules.identity.router import router as identity_router
from recruitai.modules.jobs.router import router as jobs_router
from recruitai.modules.letters.router import router as letters_router
from recruitai.modules.matching.router import router as matching_router
from recruitai.modules.privacy.router import router as privacy_router
from recruitai.modules.radar.public_router import router as radar_public_router
from recruitai.modules.radar.router import router as radar_router


def create_app() -> FastAPI:
    settings = Settings()  # type: ignore[call-arg]  # fields are populated from the environment, not passed here
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        init_db(settings)
        # Pay the first DB connection (TLS, IAM token) and the Firebase certificate download at
        # startup, in parallel, instead of inside the first user's request. Best effort.
        warming = asyncio.gather(
            warm_up(), warm_certs(settings), return_exceptions=True
        )
        try:
            yield
        finally:
            warming.cancel()
            await close_db()

    app = FastAPI(title="RecruitAI", lifespan=lifespan)
    install_error_handlers(app)
    # JSON lists compress ~5-10x; Starlette skips text/event-stream, so the coach SSE stays live.
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(identity_router)
    app.include_router(admin_router)
    app.include_router(documents_router)
    app.include_router(signature_router)
    app.include_router(candidates_router)
    app.include_router(jobs_router)
    app.include_router(matching_router)
    app.include_router(letters_router)
    app.include_router(coach_router)
    app.include_router(applications_router)
    app.include_router(privacy_router)
    app.include_router(radar_router)
    app.include_router(radar_public_router)
    app.include_router(tasks_router)

    if settings.env != "prod":
        app.include_router(local_storage_router)

    @app.get("/health")
    def health() -> dict[str, str]:
        """Liveness only: never touches the database."""
        return {"status": "ok"}

    @app.get("/api/ping", status_code=204)
    def ping() -> Response:
        """Public and free: the web app calls it as soon as it loads, so a scaled-to-zero
        instance is already starting while the user signs in (Hosting only forwards /api/**)."""
        return Response(status_code=204)

    @app.get("/ready", response_model=None)
    async def ready(
        db: Annotated[AsyncSession, Depends(get_db)],
    ) -> dict[str, str] | JSONResponse:
        """Readiness: the database answers. No exception text in the response."""
        try:
            await db.execute(text("SELECT 1"))
        except (SQLAlchemyError, OSError):
            return JSONResponse({"status": "unavailable"}, status_code=503)
        return {"status": "ready"}

    return app


app = create_app()
