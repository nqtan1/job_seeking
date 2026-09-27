from pydantic import BaseModel, Field
from typing import List, Optional, Literal

# --- New Schemas for JobPosition ---

class CompanyInfo(BaseModel):
    name: str
    type: Literal["employer", "cabinet_recrutement", "esn", None] = Field(None, description="Employer, recruiting agency, or ESN")
    logo_url: Optional[str] = None

class Badges(BaseModel):
    contract_type: Optional[str] = None
    location: Optional[str] = Field(None, description="Short form location, e.g. Paris 1er")
    location_full: Optional[str] = Field(None, description="Full form location, e.g. 75 - Paris 1er Arrondissement")
    remote_policy: Optional[str] = None
    experience_level: Optional[str] = None
    salary: Optional[str] = Field(None, description="e.g. 40k-50k EUR/year")

class AboutCompany(BaseModel):
    summary: Optional[str] = None
    truncate_at_chars: int = 180 # Default value as per schema

class Profile(BaseModel):
    experience: Optional[str] = None
    education: Optional[str] = None
    technical_skills: List[str] = Field(default_factory=list)
    soft_skills: List[str] = Field(default_factory=list)
    nice_to_have: List[str] = Field(default_factory=list)

class Modalities(BaseModel):
    location_detail: Optional[str] = None
    start_date: Optional[str] = None
    duration: Optional[str] = None

class SourceMeta(BaseModel):
    industry: Optional[str] = None
    raw_description_hash: Optional[str] = None # Changed to Optional

# --- Existing CompensationInfo (retained) ---
class CompensationInfo(BaseModel):
    """
    Salary and benefits information
    """
    min_salary: Optional[float] = Field(None, description="Minimum salary in EUR")
    max_salary: Optional[float] = Field(None, description="Maximum salary in EUR")
    salary_currency: Optional[str] = Field(default="EUR", description="Currency")
    salary_frequency: Optional[str] = Field(None, description="Annual, Monthly, etc.")
    benefits: Optional[List[str]] = Field(None, description="Benefits: health insurance, bonus, RTT, etc.")
    variable_portion: Optional[str] = Field(None, description="Bonus, commissions, or 'part variable'")
    has_13th_month: bool = Field(default=False, description="Is there a 13ème mois?")
    rtt_days: Optional[int] = Field(None, description="Number of RTT days per year")
    meal_vouchers: Optional[bool] = Field(None, description="Tickets Restaurant / Swile")

# --- Updated JobPosition ---
class JobPosition(BaseModel):
    """
    Structured information for a job position.
    """
    job_id: Optional[str] = None # Added as per requested schema
    title: str = Field(..., description="Job position title, preserving (H/F) if present")
    company: CompanyInfo
    badges: Badges
    about_company: AboutCompany
    missions: List[str] = Field(default_factory=list, description="Array of individual mission bullets, full sentences")
    tech_stack: List[str] = Field(default_factory=list, description="Short tags/keywords only, no sentences")
    working_methods: List[str] = Field(default_factory=list, description="e.g. Agile, Travail collaboratif")
    profile: Profile
    modalities: Modalities
    compensation: Optional[CompensationInfo] = None # Retained, as it's detailed
    source_meta: SourceMeta
    job_description_text: Optional[str] = Field(None, description="The full, raw job description text") # Added field


# ==========================================
# PHASE 2: JOB ANALYSIS SCHEMA (retained as is)
# ==========================================

class SkillDemand(BaseModel):
    """Skill analysis from job perspective"""
    name: str
    importance: Literal["Critical", "High", "Medium", "Low"]
    current_market_value: Literal["In-demand", "Standard", "Declining", "Emerging"]
    difficulty_to_acquire: Literal["Easy", "Moderate", "Difficult", "Very Difficult"]

class RoleComplexity(BaseModel):
    """Assessment of role difficulty"""
    level: Literal["Entry", "Mid", "Senior", "Lead", "Director"]
    complexity_score: int = Field(..., ge=1, le=10, description="1-10 scale")
    decision_making_level: str
    stakeholder_management: str

class MarketPosition(BaseModel):
    """Market analysis for this role"""
    competitiveness: Literal["High demand, Low supply", "Balanced", "Low demand, High supply"]
    salary_competitiveness: Literal["Below market", "At market", "Above market"]
    skill_scarcity_level: Literal["Abundant", "Common", "Scarce", "Very scarce"]

class CandidateAnalysis(BaseModel):
    """Job analysis from candidate perspective"""
    job_title: str
    company: str
    
    # Career Growth
    career_growth_potential: str = Field(..., description="How this role contributes to career development")
    skill_development_opportunities: List[str] = Field(default_factory=list, description="Skills you can learn/develop")
    
    # Compensation & Work-Life Balance
    compensation_assessment: str = Field(..., description="Salary analysis relative to market")
    work_life_balance: str = Field(..., description="Assessment of work-life balance indicators")
    benefits_assessment: Optional[str] = Field(None, description="Analysis of offered benefits")
    
    # Role Characteristics
    role_difficulty: Literal["Beginner-Friendly", "Moderate", "Challenging", "Expert-Level"]
    required_effort_level: Literal["Low", "Medium", "High", "Very High"]
    
    # Team & Environment
    team_dynamics: Optional[str] = Field(None, description="What you can infer about team culture")
    company_culture_fit: str = Field(..., description="Analysis of company and role fit")
    
    # Candidate Suitability
    ideal_candidate_profile: str = Field(..., description="Profile that would thrive in this role")
    
    # Pros & Cons
    major_pros: List[str] = Field(default_factory=list, description="What's attractive about this role")
    major_cons: List[str] = Field(default_factory=list, description="Potential challenges or concerns")
    
    # Summary
    candidate_recommendation: str = Field(..., description="Should a candidate consider this role?")


class RecruiterAnalysis(BaseModel):
    """Strategic job analysis for recruiters"""
    job_title: str
    company: str
    
    # Role Assessment
    role_complexity: RoleComplexity
    critical_skills: List[SkillDemand]
    
    # Market Context
    market_position: MarketPosition
    competitive_advantage: Optional[str] = Field(None, description="What makes this role attractive")
    potential_challenges: Optional[List[str]] = Field(None, description="Difficulties in finding candidates")
    
    # Candidate Profile
    ideal_candidate_profile: str
    must_have_requirements: List[str]
    nice_to_have_requirements: List[str]
    
    # Risk Assessment
    hiring_difficulty: Literal["Low", "Medium", "High", "Very High"]
    time_to_fill_estimate: Optional[str] = Field(None, description="Estimated hiring duration")
    
    # Summary
    recruiter_notes: str


class JobAnalysis(BaseModel):
    """Combined job analysis from both candidate and recruiter perspectives"""
    job_information: JobPosition = Field(..., description="Extracted job information")
    candidate_analysis: CandidateAnalysis = Field(..., description="Analysis from candidate perspective")
    recruiter_analysis: RecruiterAnalysis = Field(..., description="Analysis from recruiter perspective")
