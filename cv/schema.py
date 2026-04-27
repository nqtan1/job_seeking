from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional


# Personal Information schema 
class PersonalInfo(BaseModel):
    """
    Personal information from CV
    """
    name: str = Field(..., description="Full name")
    email: Optional[EmailStr] = Field(None, description="Email address")
    phone: str = Field(..., description="Phone number")
    address: str = Field(..., description="Physical address")
    linkedin: Optional[str] = Field(None, description="LinkedIn profile url")
    github: Optional[str] = Field(None, description="Github profile url")
    website: Optional[str] = Field(None, description="Personal website/portfolio")


# Formation/Education schema
class Formation(BaseModel):
    """
    Education/Formation information
    """
    degree: str = Field(..., description="Degree type (e.g, Bachelor, Master, PhD)")
    field: str = Field(..., description="Field of study (e.g, Computer Science, Communication, ...)")
    institution: str = Field(..., description="University/School name")
    gpa: Optional[float] = Field(None, description="GPA (0.0-4.0 or 0.0-10.0 or 0.0-20.0)")
    subjects: Optional[List[str]] = Field(None, description="List of main subjects in the school/university")
    description: Optional[str] = Field(None, description="Additional details")
    
# Experience Schema 
class Experience(BaseModel):
    """
    Work Experience information
    """
    job_title: str = Field(..., description="Job position/title")
    company: str = Field(..., description="Company/Laboratory name")
    start_date: Optional[str] = Field(None, description="Start date")
    end_date: Optional[str] = Field(None, description="End date (or 'Present')")
    location: Optional[str] = Field(None, description="Work location")
    description: Optional[str] = Field(None, description="Job responsibilities and achievements")
    skills_used: Optional[List[str]] = Field(None, description="Technologies/skills used")

# Reference Schema
class Reference(BaseModel):
    """Professional reference"""
    name: str = Field(..., description="Reference name")
    position: Optional[str] = Field(None, description="Reference job title")
    company: Optional[str] = Field(None, description="Reference company")
    email: Optional[EmailStr] = Field(None, description="Reference email")
    phone: Optional[str] = Field(None, description="Reference phone")


# Skill Schema
class Skill(BaseModel):
    """Skill information"""
    name: str = Field(..., description="Skill name (e.g., Python, Project Management)")
    category: Optional[str] = Field(None, description="Category (Technical, Soft, Language, etc.)")
    level: Optional[str] = Field(None, description="Proficiency level (Beginner, Intermediate, Advanced, Expert)")


# Main CV Schema
class CVInformation(BaseModel):
    """Complete CV data extracted from document"""
    personal_info: PersonalInfo = Field(..., description="Personal information")
    formations: List[Formation] = Field(default_factory=list, description="Education history")
    experiences: List[Experience] = Field(default_factory=list, description="Work experience")
    skills: List[Skill] = Field(default_factory=list, description="Skills list")
    references: Optional[List[Reference]] = Field(None, description="Professional references (optional)")
    description: Optional[str] = Field(None, description="Professional summary or motivation letter (optional)")
    