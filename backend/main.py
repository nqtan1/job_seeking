from pathlib import Path
import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, PlainTextResponse
from cv.route import router as cv_router
from fit.route import router as fit_router
from hr.route import router as hr_router
from jobs.route import router as jobs_router
from motivation_letter.route import router as motivation_letter_router

app = FastAPI(
    title="Job Seeking CV API",
    description="API to upload CV files and extract job descriptions",
    version="0.2.0"
)

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