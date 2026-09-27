from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from domain.cv.schema import CVInformation
from domain.jobs.schema import JobPosition
from domain.fit.schema import FitCheck, InterviewPreparationKit


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class CareerChatRequest(BaseModel):
    candidate_cv: CVInformation
    job_information: Optional[JobPosition] = Field(
        default=None, description="The job currently under discussion, if any"
    )
    fit_check: Optional[FitCheck] = Field(
        default=None, description="Previously computed fit analysis, if any"
    )
    interview_kit: Optional[InterviewPreparationKit] = Field(
        default=None, description="Previously generated mock interview kit, if any"
    )
    message: str = Field(..., description="The candidate's new chat message")
    history: List[ChatMessage] = Field(
        default_factory=list, description="Prior turns in this conversation, oldest first"
    )


class CareerChatResponse(BaseModel):
    reply: str
