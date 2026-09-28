from fastapi import FastAPI

from recruitai.config import Settings


def create_app() -> FastAPI:
    Settings()  # type: ignore[call-arg]  # fields are populated from the environment, not passed here

    app = FastAPI(title="RecruitAI")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
