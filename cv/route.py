from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException
from typing import List

router = APIRouter()

# Allowed file extensions 
ALLOWED_EXTENSIONS = {
    ".pdf", ".img", ".txt", ".jpg", ".jpeg"
}

# Maximum size 
MAX_FILE_SIZE = 10 * 1024 * 1024

# Path to store CV files
UPLOAD_DIR = Path(__file__).parent.parent / "db/cv/uploads"
UPLOAD_DIR.mkdir(parents=True,exist_ok=True)

@router.post("/upload")
async def upload_cv(file: UploadFile = File(...)):
    """
    Upload a CV file
    
    Supported formats: PDF, IMG, TXT, JPG, JPEG
    Max size: 10MB
    """
    file_extension = Path(file.filename).suffix.lower()
    # Valid file extension
    if file_extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type not allowed. Allowed type: {', '.join(ALLOWED_EXTENSIONS)}"
        )
        
    # Valid file size 
    file_content= await file.read()
    if len(file_content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File size exceed 10MB limit"
        )
        
    await file.seek(0)
    
    # Save file 
    file_path = UPLOAD_DIR / file.filename
    with open(file_path, "wb") as f:
        f.write(file_content)
        
    return {
        "message": "File upload successfully!",
        "filename": file.filename,
        "size": len(file_content),
        "path": str(file_path)
    }
    
    