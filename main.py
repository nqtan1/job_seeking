import uvicorn
from fastapi import FastAPI
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

@app.get("/")
def read_root():
    return {"message": "Welcome to Job Seeking CV API"}

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