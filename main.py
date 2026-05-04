import uvicorn
from fastapi import FastAPI
from cv.route import router as cv_router
from jobs.route import router as jobs_router

app = FastAPI(
    title="Job Seeking CV API",
    description="API to upload CV files and extract job descriptions",
    version="0.2.0"
)

# Include CV routes
app.include_router(cv_router, prefix="/api/cv", tags=["CV"])

# Include Jobs routes
app.include_router(jobs_router, prefix="/api/jobs", tags=["Jobs"])

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