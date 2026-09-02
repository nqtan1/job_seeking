from pydantic import BaseModel, Field
from typing import Optional, Literal, List
from datetime import datetime
from cv.schema import CVInformation
from jobs.schema import JobPosition, CandidateAnalysis

class MotivationLetterRequest(BaseModel):
    """
    Input structure for motivation letter generation
    """
    
    # Required: Core data
    cv_info: CVInformation
    job_info: JobPosition
    
    # Required: User Preferences
    job_type: Literal["startup", "phd", "corporation"] = Field(..., description="Type of company/position")
    language: Literal["en","fr"] = Field(default="fr", description="Letter language")
    tone: Literal["professional", "academic", "formal"] = Field(
        default="professional", description="Letter tone"
    )
    return_format: Literal["txt", "latex"] = Field(default="txt", description="Output format")
    
    # Optional: Analysis and Custom context
    candidate_analysis: Optional[CandidateAnalysis] = Field(None, description="Pre-computed job fit analysis (optional)"
    )
    custom_context: Optional[str] = Field(None, description="User-provided additional context or requirements")
    
    
class MotivationLetterMetadata(BaseModel):
    """Metadata about the generated letter"""
    
    generated_at: datetime
    job_type: str
    language: str
    tone: str
    format: str
    system_prompt_used: str  # Which prompt template was used
    llm_model: str
    token_usage: Optional[dict] = None
    

class MotivationLetter(BaseModel):
    """
    Output structure for motivation letter
    """
    content: str = Field(..., description="The actual motivation letter text")
    metadata: MotivationLetterMetadata