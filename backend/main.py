from pathlib import Path
import uuid
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from api.cv import router as cv_router
from api.fit import router as fit_router
from api.hr import router as hr_router
from api.motivation_letter import router as motivation_letter_router
from api.jobs import router as jobs_router
from api.applications import router as applications_router

from utils.logger import get_logger, request_id_var, tenant_id_var

main_logger = get_logger("main")

app = FastAPI(
    title="Job Seeking CV API",
    description="API to upload CV files and extract job descriptions",
    version="0.2.0"
)


@app.middleware("http")
async def observability_correlation_middleware(request: Request, call_next):
    # 1. Generate or retrieve request_id
    req_id = request.headers.get("X-Request-Id") or request.headers.get("x-request-id") or str(uuid.uuid4())
    request_id_var.set(req_id)
    
    # 2. Extract tenant_id if present in headers or query params
    ten_id = request.headers.get("X-Tenant-Id") or request.headers.get("x-tenant-id") or request.query_params.get("tenant_id")
    if ten_id:
        tenant_id_var.set(ten_id)
        
    main_logger.info(
        "Request started",
        extra={
            "event": "request_started",
            "status": "started",
            "method": request.method,
            "url": str(request.url),
        }
    )
    
    try:
        response = await call_next(request)
        response.headers["X-Request-Id"] = req_id
        
        main_logger.info(
            "Request finished",
            extra={
                "event": "request_finished",
                "status": "success",
                "status_code": response.status_code,
            }
        )
        return response
    except Exception as exc:
        main_logger.error(
            "Request crashed",
            exc_info=True,
            extra={
                "event": "request_failed",
                "status": "failed",
                "error": str(exc),
            }
        )
        raise
    finally:
        # Reset contextvars
        request_id_var.set(None)
        tenant_id_var.set(None)


# Include CV routes
app.include_router(cv_router, prefix="/api/cv", tags=["CV"])

# Include Jobs routes
app.include_router(jobs_router, prefix="/api/jobs", tags=["Jobs"])

# Include Fit routes
app.include_router(fit_router, prefix="/api/fit", tags=["Fit"])

# Include HR routes
app.include_router(hr_router, prefix="/api/hr", tags=["HR"])

# Include Motivation Letter routes
app.include_router(motivation_letter_router, prefix="/api/motivation-letter", tags=["Motivation Letter"])  

# Include Applications routes
app.include_router(applications_router, prefix="/api/applications", tags=["Applications"])


@app.get("/api/jobs/metrics")
def get_metrics_endpoint():
    from workers.background import get_job_metrics
    return get_job_metrics()


@app.get("/", response_class=HTMLResponse)
def read_root():
    html_path = Path(__file__).parent.parent / "frontend" / "index.html"
    if html_path.exists():
        return html_path.read_text(encoding="utf-8")
    return "<h1>RecruitAI Console: frontend/index.html not found</h1>"

@app.get("/{filename}.js", response_class=PlainTextResponse)
def get_js_file(filename: str):
    js_path = Path(__file__).parent.parent / "frontend" / f"{filename}.js"
    if js_path.exists():
        return PlainTextResponse(content=js_path.read_text(encoding="utf-8"), media_type="application/javascript")
    return PlainTextResponse(content=f"console.error('frontend/{filename}.js not found')", media_type="application/javascript", status_code=404)

@app.get("/health")
def health_check():
    return {"status": "ok"}

def main():
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000
    )

if __name__ == "__main__":
    main()