from fastapi import FastAPI

from recruitai.config import Settings


def create_app() -> FastAPI:
    Settings()

    app = FastAPI(title="RecruitAI")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
