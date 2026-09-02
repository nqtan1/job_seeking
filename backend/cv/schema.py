from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Literal

# ==========================================
# PHASE 1: EXTRACTION SCHEMA (Raw Data)
# Goal: Convert PDF/Docx text into structured JSON without judgment.
# ==========================================

class PersonalInfo(BaseModel):
    """Raw personal information extracted from CV"""
    name: str = Field(..., description="Full name")
    email: Optional[EmailStr] = Field(None, description="Email address")
    phone: str = Field(..., description="Phone number")
    address: Optional[str] = Field(None, description="Physical address")
    linkedin: Optional[str] = Field(None, description="LinkedIn profile url")
    github: Optional[str] = Field(None, description="Github profile url")
    website: Optional[str] = Field(None, description="Personal website/portfolio")

class Formation(BaseModel):
    """Raw educational history"""
    degree: str = Field(..., description="Degree type (e.g., Bachelor, Master, PhD)")
    field: str = Field(..., description="Field of study")
    institution: str = Field(..., description="University/School name")
    gpa: Optional[float] = Field(None, description="GPA score")
    subjects: Optional[List[str]] = Field(None, description="Main subjects studied")
    description: Optional[str] = Field(None, description="Additional context about education")

class Experience(BaseModel):
    """Raw work history"""
    job_title: str = Field(..., description="Job position/title")
    company: str = Field(..., description="Company or Laboratory name")
    start_date: Optional[str] = Field(None, description="Start date")
    end_date: Optional[str] = Field(None, description="End date or 'Present'")
    location: Optional[str] = Field(None, description="Work location")
    description: Optional[str] = Field(None, description="Responsibilities and achievements")
    skills_used: Optional[List[str]] = Field(None, description="Technologies mentioned in this role")

class RawSkill(BaseModel):
    """Raw skill mentioned by candidate"""
    name: str = Field(..., description="Skill name")
    category: Optional[str] = Field(None, description="Technical, Soft, etc.")

class CVInformation(BaseModel):
    """The final object for Phase 1: Structured Raw Data"""
    personal_info: PersonalInfo
    formations: List[Formation] = Field(default_factory=list)
    experiences: List[Experience] = Field(default_factory=list)
    skills: List[RawSkill] = Field(default_factory=list)
    summary: Optional[str] = Field(None, description="Professional summary or cover letter text")

# ==========================================
# PHASE 2: ANALYSIS SCHEMA (Recruiter Intelligence)
# Goal: Evaluate the raw data and generate strategic insights.
# ==========================================

class Competency(BaseModel):
    """Evaluated skill: Recruiter's judgment on proficiency and relevance"""
    name: str
    level: Literal["Beginner", "Intermediate", "Advanced", "Expert"]
    years_of_experience: float
    is_core: bool = Field(False, description="Is this critical for the specific role?")

class Achievement(BaseModel):
    """Quantified impact found during analysis"""
    description: str
    metric: Optional[str] = Field(None, description="E.g., 20% increase, 50ms latency reduction")
    context: str

class Strength(BaseModel):
    area: str
    description: str
    evidence: str = Field(..., description="Direct quote or fact from Phase 1 data")

class Weakness(BaseModel):
    area: str
    description: str
    severity: Literal["low", "medium", "high"]
    mitigation: Optional[str]

class BaseCandidateAnalysis(BaseModel):
    """General evaluation framework for any role"""
    candidate_id: str
    strengths: List[Strength]
    weaknesses: List[Weakness]
    evaluated_competencies: List[Competency]
    top_achievements: List[Achievement]
    
    cultural_fit_score: int = Field(..., ge=0, le=10)
    communication_style: str
    hiring_risk_level: Literal["Low", "Medium", "High"]
    career_trajectory: Literal[
        "Jeune Diplômé",
        "Early Career Growth", 
        "Rising Star",
        "Stable Performer",
        "Mid-Career Plateau",
        "Senior Plateau",
        "Declining"
    ]
    recruiter_summary: str

class AIEngineerAnalysis(BaseCandidateAnalysis):
    """Specialized evaluation for AI roles in France/EU"""
    math_and_logic_depth: int = Field(..., ge=0, le=10)
    mlops_readiness: bool
    sota_knowledge: List[str]
    academic_prestige: bool = Field(False, description="Grande École or Top Research Lab")
    gdpr_awareness: bool
    
    verdict: Literal["Fast-track", "Interview", "Waitlist", "Reject"]
    hiring_manager_note: str