import io

from pypdf import PdfReader
from pypdf.errors import PdfReadError
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import Resume
from app.services.errors import BadRequest, NotFound

MAX_PDF_BYTES = 5 * 1024 * 1024


def extract_pdf_text(data: bytes) -> str:
    if len(data) > MAX_PDF_BYTES:
        raise BadRequest("PDF is too large (max 5 MB).")
    try:
        reader = PdfReader(io.BytesIO(data))
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
    except (PdfReadError, ValueError, KeyError) as e:
        raise BadRequest("Could not read that PDF. Try pasting the text instead.") from e
    text = "\n".join(line.rstrip() for line in text.splitlines()).strip()
    if len(text) < 50:
        raise BadRequest(
            "Couldn't find enough text in that PDF (it may be a scanned image). "
            "Please paste your resume text instead."
        )
    return text


def create_resume(db: Session, user_id: int, content: str) -> Resume:
    """New resumes become the active one (one active resume per user)."""
    db.execute(update(Resume).where(Resume.user_id == user_id).values(is_active=False))
    resume = Resume(user_id=user_id, content=content.strip(), is_active=True)
    db.add(resume)
    db.commit()
    db.refresh(resume)
    return resume


def list_resumes(db: Session, user_id: int) -> list[Resume]:
    return list(db.scalars(
        select(Resume).where(Resume.user_id == user_id).order_by(Resume.created_at.desc(), Resume.id.desc())
    ))


def get_active(db: Session, user_id: int) -> Resume | None:
    return db.scalar(select(Resume).where(Resume.user_id == user_id, Resume.is_active.is_(True)))


def _get_owned(db: Session, user_id: int, resume_id: int) -> Resume:
    resume = db.get(Resume, resume_id)
    if resume is None or resume.user_id != user_id:
        raise NotFound("Resume not found.")
    return resume


def activate(db: Session, user_id: int, resume_id: int) -> Resume:
    resume = _get_owned(db, user_id, resume_id)
    db.execute(update(Resume).where(Resume.user_id == user_id).values(is_active=False))
    resume.is_active = True
    db.commit()
    db.refresh(resume)
    return resume


def delete(db: Session, user_id: int, resume_id: int) -> None:
    resume = _get_owned(db, user_id, resume_id)
    was_active = resume.is_active
    db.delete(resume)
    db.commit()
    if was_active:  # promote the most recent remaining resume
        remaining = list_resumes(db, user_id)
        if remaining:
            activate(db, user_id, remaining[0].id)
