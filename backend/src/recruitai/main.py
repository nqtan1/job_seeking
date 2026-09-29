from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.config import Settings
from recruitai.core.db import close_db, get_db, init_db
from recruitai.core.error_handlers import install_error_handlers
from recruitai.core.logging import configure_logging
from recruitai.core.middleware import RequestContextMiddleware


def create_app() -> FastAPI:
    settings = Settings()  # type: ignore[call-arg]  # fields are populated from the environment, not passed here
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        init_db(settings)
        try:
            yield
        finally:
            await close_db()

    app = FastAPI(title="RecruitAI", lifespan=lifespan)
    install_error_handlers(app)
    app.add_middleware(RequestContextMiddleware)

    @app.get("/health")
    def health() -> dict[str, str]:
        """Liveness only: never touches the database."""
        return {"status": "ok"}

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
