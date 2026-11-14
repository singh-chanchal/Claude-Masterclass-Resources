from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import (
    ApplicationIn, ApplicationOut, ApplicationUpdate, InterviewIn, InterviewOut, StageChangeIn,
)
from app.services import application_service as svc

router = APIRouter(prefix="/api", tags=["applications"])


@router.get("/applications", response_model=list[ApplicationOut])
def list_applications(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return svc.list_applications(db, user.id)


@router.post("/applications", response_model=ApplicationOut, status_code=status.HTTP_201_CREATED)
def create_application(body: ApplicationIn, user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    return svc.create(db, user.id, body.model_dump())


@router.get("/applications/{app_id}", response_model=ApplicationOut)
def get_application(app_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return svc.get_owned(db, user.id, app_id)


@router.patch("/applications/{app_id}", response_model=ApplicationOut)
def update_application(app_id: int, body: ApplicationUpdate, user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    return svc.update_fields(db, user.id, app_id, body.model_dump(exclude_unset=True))


@router.patch("/applications/{app_id}/stage", response_model=ApplicationOut)
def change_stage(app_id: int, body: StageChangeIn, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    return svc.change_stage(db, user.id, app_id, body.stage)


@router.delete("/applications/{app_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_application(app_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    svc.delete(db, user.id, app_id)


@router.post("/applications/{app_id}/interviews", response_model=InterviewOut,
             status_code=status.HTTP_201_CREATED)
def add_interview(app_id: int, body: InterviewIn, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    data = body.model_dump()
    # Store as naive local time so "this week" matches what the user typed.
    data["scheduled_at"] = data["scheduled_at"].replace(tzinfo=None)
    return svc.add_interview(db, user.id, app_id, data)


@router.delete("/interviews/{interview_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_interview(interview_id: int, user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    svc.delete_interview(db, user.id, interview_id)
