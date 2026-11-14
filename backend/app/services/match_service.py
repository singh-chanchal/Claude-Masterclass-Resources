import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.client import AIClient
from app.models import Application, Match, Stage
from app.services import resume_service
from app.services.errors import BadRequest, NotFound


def to_out(match: Match, application_id: int | None = None, company=None, role=None) -> dict:
    return {
        "id": match.id,
        "resume_id": match.resume_id,
        "job_description": match.job_description,
        "fit_score": match.fit_score,
        "missing_skills": json.loads(match.missing_skills or "[]"),
        "suggested_bullets": json.loads(match.suggested_bullets or "[]"),
        "company_guess": company,
        "role_guess": role,
        "application_id": application_id,
        "created_at": match.created_at,
    }


def run_match(db: Session, ai: AIClient, user_id: int, job_description: str) -> dict:
    resume = resume_service.get_active(db, user_id)
    if resume is None:
        raise BadRequest("Add your resume first — the match compares it with the job description.")
    result = ai.match_resume(resume.content, job_description.strip())
    match = Match(
        user_id=user_id,
        resume_id=resume.id,
        job_description=job_description.strip(),
        fit_score=result.fit_score,
        missing_skills=json.dumps(result.missing_skills),
        suggested_bullets=json.dumps(result.suggested_bullets),
    )
    db.add(match)
    db.commit()
    db.refresh(match)
    return to_out(match, company=result.company, role=result.role)


def _application_ids_by_match(db: Session, user_id: int) -> dict[int, int]:
    rows = db.execute(
        select(Application.match_id, Application.id).where(
            Application.user_id == user_id, Application.match_id.is_not(None)
        )
    )
    return {m: a for m, a in rows}


def list_matches(db: Session, user_id: int, limit: int = 20) -> list[dict]:
    matches = db.scalars(
        select(Match).where(Match.user_id == user_id)
        .order_by(Match.created_at.desc(), Match.id.desc()).limit(limit)
    )
    app_ids = _application_ids_by_match(db, user_id)
    return [to_out(m, app_ids.get(m.id)) for m in matches]


def save_as_application(db: Session, user_id: int, match_id: int, company: str, role: str,
                        job_url: str | None, notes: str | None) -> Application:
    match = db.get(Match, match_id)
    if match is None or match.user_id != user_id:
        raise NotFound("Match not found.")
    existing = db.scalar(select(Application).where(Application.match_id == match_id))
    if existing:
        raise BadRequest("This match is already saved to your pipeline.")
    app = Application(
        user_id=user_id, match_id=match_id, company=company.strip(), role=role.strip(),
        stage=Stage.WISHLIST, job_url=(job_url or "").strip() or None,
        notes=(notes or "").strip() or f"AI fit score: {match.fit_score}/100",
    )
    db.add(app)
    db.commit()
    db.refresh(app)
    return app
