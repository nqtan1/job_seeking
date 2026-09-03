from pydantic import BaseModel, Field
from typing import List, Optional, Literal

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
    
class JobRequirements(BaseModel):
    """
    Required skills and experience
    """
    required_skills: List[str] = Field(default_factory=list, description="Required technical skills")
    preferred_skills: Optional[List[str]] = Field(None, description="Nice-to-have skills")
    experience_level: Optional[str] = Field(None, description="Junior, Mid-level, Senior, or years of experience")
    languages: Optional[List[str]] = Field(None, description="Required languages (e.g., French B2, English B1)")
    certifications: Optional[List[str]] = Field(None, description="Certifications or degrees required")
    education_level: Optional[str] = Field(None, description="Minimum degree: Bac+2, Bac+5, Grande École, etc.")
    years_of_experience: Optional[int] = Field(None, description="Specific number of years requested")
    soft_skills: Optional[List[str]] = Field(None, description="Leadership, Communication, etc.")


class JobPosition(BaseModel):
    """
    Basic information for job position (in French)
    """
    # Basic information
    job_title: str = Field(..., description="Job position")
    company: str = Field(..., description="Company name")
    laboratory: Optional[str] = Field(None, description="Laboratory name")
    location: str = Field(..., description="City and ZIP code if available (e.g., Paris 75008)")
    remote_policy: Optional[str] = Field(None, description="e.g., '2 jours/semaine', 'Full Remote'")
    
    # Contract details
    contract_type: Literal["CDI", "CDD", "Stage", "Alternance", "Freelance", "PhD"] = Field(...)
    contract_duration: Optional[str] = Field(None, description="For CDD: duration or end date")
    start_date: Optional[str] = Field(None, description="Expected start date")
    
    # Compensation 
    compensation: Optional[CompensationInfo] = Field(None, description="Salary and benefits")
    
    # Requirements
    requirements: JobRequirements = Field(default_factory=JobRequirements, description="Skills and experience")
    
    # Responsibilities
    responsibilities: Optional[List[str]] = Field(None, description="Main duties and responsibilities")
    
    # Additional Info
    team_size: Optional[str] = Field(None, description="Team or department size")
    reporting_to: Optional[str] = Field(None, description="Position they report to")
    job_description_text: Optional[str] = Field(None, description="Full original job description")
    is_cadre: Optional[bool] = Field(None, description="Executive status (Statut Cadre)")
    convention_collective: Optional[str] = Field(None, description="Applicable collective agreement (e.g., Syntec, Metallurgy)")
    trial_period: Optional[str] = Field(None, description="Période d'essai duration")
    company_description: Optional[str] = Field(None, description="About the company")
    industry: Optional[str] = Field(None, description="Industry/sector")

# ==========================================
# PHASE 2: JOB ANALYSIS SCHEMA
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