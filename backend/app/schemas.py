from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models import Stage


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---- auth ----
class SignupIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)  # bcrypt uses the first 72 bytes


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=72)  # same rule as SignupIn


class UserOut(ORM):
    id: int
    name: str
    email: str
    created_at: datetime | None = None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ---- resumes ----
class ResumeTextIn(BaseModel):
    content: str = Field(min_length=50, max_length=50_000)


class ResumeOut(ORM):
    id: int
    content: str
    is_active: bool
    created_at: datetime | None = None


# ---- matches ----
class MatchIn(BaseModel):
    job_description: str = Field(min_length=50, max_length=30_000)


class MatchOut(BaseModel):
    id: int
    resume_id: int
    job_description: str
    fit_score: int
    missing_skills: list[str]
    suggested_bullets: list[str]
    company_guess: str | None = None
    role_guess: str | None = None
    application_id: int | None = None
    created_at: datetime | None = None


class SaveMatchIn(BaseModel):
    company: str = Field(min_length=1, max_length=200)
    role: str = Field(min_length=1, max_length=200)
    job_url: str | None = None
    notes: str | None = None


# ---- applications ----
class InterviewIn(BaseModel):
    scheduled_at: datetime
    round: str | None = Field(default=None, max_length=100)
    notes: str | None = None


class InterviewOut(ORM):
    id: int
    application_id: int
    scheduled_at: datetime
    round: str | None
    notes: str | None


class ApplicationIn(BaseModel):
    company: str = Field(min_length=1, max_length=200)
    role: str = Field(min_length=1, max_length=200)
    stage: Stage = Stage.WISHLIST
    job_url: str | None = None
    applied_date: date | None = None
    notes: str | None = None

    @field_validator("job_url", "notes")
    @classmethod
    def blank_to_none(cls, v):
        return v.strip() or None if isinstance(v, str) else v


class ApplicationUpdate(BaseModel):
    company: str | None = Field(default=None, min_length=1, max_length=200)
    role: str | None = Field(default=None, min_length=1, max_length=200)
    job_url: str | None = None
    applied_date: date | None = None
    notes: str | None = None

    @field_validator("job_url", "notes")
    @classmethod
    def blank_to_none(cls, v):
        return v.strip() or None if isinstance(v, str) else v


class StageChangeIn(BaseModel):
    stage: Stage


class ApplicationOut(ORM):
    id: int
    match_id: int | None
    company: str
    role: str
    stage: Stage
    job_url: str | None
    applied_date: date | None
    notes: str | None
    created_at: datetime | None
    updated_at: datetime | None
    interviews: list[InterviewOut] = []


# ---- dashboard ----
class UpcomingInterview(BaseModel):
    id: int
    application_id: int
    company: str
    role: str
    scheduled_at: datetime
    round: str | None


class DashboardOut(BaseModel):
    total_applications: int
    by_stage: dict[str, int]
    interviews_this_week: int
    upcoming_interviews: list[UpcomingInterview]
    applications_sent: int
    applications_with_response: int
    response_rate: float | None  # percent, None when nothing sent yet
    week_start: date
    week_end: date
