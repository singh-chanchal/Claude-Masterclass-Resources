from fastapi import APIRouter, Depends, File, UploadFile, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import ResumeOut, ResumeTextIn
from app.services import resume_service
from app.services.errors import BadRequest

router = APIRouter(prefix="/api/resumes", tags=["resumes"])


@router.get("", response_model=list[ResumeOut])
def list_resumes(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return resume_service.list_resumes(db, user.id)


@router.get("/active", response_model=ResumeOut | None)
def active_resume(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return resume_service.get_active(db, user.id)


@router.post("/text", response_model=ResumeOut, status_code=status.HTTP_201_CREATED)
def paste_resume(body: ResumeTextIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return resume_service.create_resume(db, user.id, body.content)


@router.post("/upload", response_model=ResumeOut, status_code=status.HTTP_201_CREATED)
async def upload_resume(file: UploadFile = File(...), user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    name = (file.filename or "").lower()
    if not (name.endswith(".pdf") or file.content_type == "application/pdf"):
        raise BadRequest("Please upload a PDF file.")
    data = await file.read(resume_service.MAX_PDF_BYTES + 1)
    text = resume_service.extract_pdf_text(data)
    return resume_service.create_resume(db, user.id, text)


@router.post("/{resume_id}/activate", response_model=ResumeOut)
def activate(resume_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return resume_service.activate(db, user.id, resume_id)


@router.delete("/{resume_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(resume_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    resume_service.delete(db, user.id, resume_id)
