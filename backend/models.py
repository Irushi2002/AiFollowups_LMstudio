from pydantic import BaseModel, Field, validator
from typing import List, Optional, Any
from datetime import datetime
from enum import Enum

class SessionStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"

class WorkStatus(str, Enum):
    WORKING = "working"
    LEAVE = "leave"
    WFH = "wfh"  # Work from home

class WorkUpdateCreate(BaseModel):
    user_id: str = Field(..., description="User/Intern ID - required for all operations")
    stack: str = Field(..., description="Technology stack being worked on")
    task: str = Field(..., description="Description of work completed/being done")
    progress: Optional[str] = Field(default="No challenges faced", description="Challenges or progress notes")
    blockers: Optional[str] = Field(default="No specific plans", description="Blockers or plans for tomorrow")
    status: WorkStatus = Field(default=WorkStatus.WORKING, description="Current work status")
    submittedAt: Optional[datetime] = Field(default_factory=datetime.utcnow)

    @validator("user_id", "stack", "task")
    def check_non_empty(cls, v):
        if not v or not v.strip():
            raise ValueError("Field cannot be empty or whitespace")
        return v.strip()

    @validator("user_id")
    def validate_user_id_format(cls, v):
        """Ensure user_id is valid format"""
        if not v or len(v.strip()) < 1:
            raise ValueError("user_id must be at least 1 character long")
        # Remove any potential MongoDB ObjectId formatting issues
        cleaned_id = v.strip().replace(" ", "").replace("\n", "")
        if not cleaned_id:
            raise ValueError("user_id cannot be empty after cleaning")
        return cleaned_id

class WorkUpdate(WorkUpdateCreate):
    id: Optional[str] = Field(default=None, alias="_id")
    internId: Optional[str] = Field(default=None)  # Will be set from user_id
    date: Optional[str] = Field(default=None)  # LogBook date field
    followupCompleted: Optional[bool] = Field(default=False)
    session_date_id: Optional[str] = Field(default=None)
    
    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat()}

class FollowupSessionCreate(BaseModel):
    user_id: str = Field(..., description="User/Intern ID for session ownership")
    workUpdateId: Optional[str] = None
    questions: List[str] = Field(..., description="Follow-up questions to ask")
    answers: Optional[List[str]] = Field(default_factory=list)
    status: SessionStatus = Field(default=SessionStatus.PENDING)
    createdAt: Optional[datetime] = Field(default_factory=datetime.utcnow)
    completedAt: Optional[datetime] = None
    session_date: Optional[str] = Field(default=None)

    @validator("user_id")
    def check_user_id_non_empty(cls, v):
        if not v or not v.strip():
            raise ValueError("user_id cannot be empty")
        return v.strip()

class FollowupSession(FollowupSessionCreate):
    id: Optional[str] = Field(alias="_id")
    internId: Optional[str] = Field(default=None)  # Will be set from user_id
    
    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat()}

class FollowupAnswersUpdate(BaseModel):
    user_id: str = Field(..., description="User/Intern ID for session verification")
    answers: List[str] = Field(..., description="Answers to the follow-up questions")

    @validator("user_id")
    def check_user_id_non_empty(cls, v):
        if not v or not v.strip():
            raise ValueError("user_id cannot be empty")
        return v.strip()

    @validator("answers")
    def check_answers_complete(cls, v):
        if not v or len(v) != 3:
            raise ValueError("Exactly 3 answers are required")
        for i, answer in enumerate(v):
            if not answer or not answer.strip():
                raise ValueError(f"Answer {i+1} cannot be empty")
        return [answer.strip() for answer in v]

class GenerateQuestionsRequest(BaseModel):
    user_id: str = Field(..., description="User/Intern ID for generating questions")

    @validator("user_id")
    def check_user_id_non_empty(cls, v):
        if not v or not v.strip():
            raise ValueError("user_id cannot be empty")
        return v.strip()

class GenerateQuestionsResponse(BaseModel):
    success: bool = True
    message: str = "Questions generated successfully"
    user_id: str
    questions: List[str]
    sessionId: str
    qualityScore: Optional[float] = None
    needsFollowup: bool = True

class TestAIResponse(BaseModel):
    success: bool
    message: str
    test_results: Optional[dict] = None

class AnalysisResponse(BaseModel):
    success: bool
    analysis: str
    user_id: str

class ErrorResponse(BaseModel):
    error: str
    message: str
    details: Optional[Any] = None
    user_id: Optional[str] = None

class QualityAnalysisRequest(BaseModel):
    user_id: str = Field(..., description="User/Intern ID for analysis")
    work_description: str = Field(..., description="Work description to analyze")

    @validator("user_id", "work_description")
    def check_non_empty(cls, v):
        if not v or not v.strip():
            raise ValueError("Field cannot be empty")
        return v.strip()

class QualityAnalysisResponse(BaseModel):
    success: bool = True
    user_id: str
    quality_score: float
    needs_followup: bool
    analysis: dict
    recommendation: str
    threshold: float

class WeeklyReportRequest(BaseModel):
    user_id: str = Field(..., description="User/Intern ID for report generation")
    start_date: Optional[str] = Field(None, description="Start date in YYYY-MM-DD format")
    end_date: Optional[str] = Field(None, description="End date in YYYY-MM-DD format")

    @validator("user_id")
    def check_user_id_non_empty(cls, v):
        if not v or not v.strip():
            raise ValueError("user_id cannot be empty")
        return v.strip()

class WeeklyReportResponse(BaseModel):
    success: bool
    user_id: str
    report: Optional[str] = None
    message: Optional[str] = None
    metadata: dict

# System Status Models
class SystemHealthResponse(BaseModel):
    status: str
    database: str
    ttl_index: str
    automatic_cleanup: str
    cleanup_task_running: bool
    quality_scoring: str
    rate_limiters: dict
    authentication: dict
    timestamp: str

class RateLimiterStatusResponse(BaseModel):
    followup_api_keys: dict
    weekly_report_api_key: dict
    overall: dict

class CleanupStatusResponse(BaseModel):
    ttl_index: dict
    manual_cleanup: dict
    recommendation: str