from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Application, Interview, Stage
from app.services.errors import NotFound

# Stages that imply the application was actually sent.
SENT_STAGES = {Stage.APPLIED, Stage.INTERVIEW, Stage.OFFER}


def list_applications(db: Session, user_id: int) -> list[Application]:
    return list(db.scalars(
        select(Application).where(Application.user_id == user_id)
        .options(selectinload(Application.interviews))
        .order_by(Application.updated_at.desc(), Application.id.desc())
    ))


def get_owned(db: Session, user_id: int, app_id: int) -> Application:
    app = db.get(Application, app_id, options=[selectinload(Application.interviews)])
    if app is None or app.user_id != user_id:
        raise NotFound("Application not found.")
    return app


def create(db: Session, user_id: int, data: dict) -> Application:
    app = Application(user_id=user_id, **data)
    _apply_stage_rules(app, Stage(app.stage))
    db.add(app)
    db.commit()
    return get_owned(db, user_id, app.id)


def update_fields(db: Session, user_id: int, app_id: int, data: dict) -> Application:
    app = get_owned(db, user_id, app_id)
    for key, value in data.items():
        setattr(app, key, value)
    db.commit()
    return get_owned(db, user_id, app_id)


def change_stage(db: Session, user_id: int, app_id: int, stage: Stage) -> Application:
    app = get_owned(db, user_id, app_id)
    if app.stage != stage:
        app.stage = stage
        _apply_stage_rules(app, stage)
        db.commit()
    return get_owned(db, user_id, app_id)


def _apply_stage_rules(app: Application, stage: Stage) -> None:
    # Spec: applied_date is "set when moved to Applied". Jumping straight to
    # Interview/Offer also implies it was sent; keep any date the user entered.
    if stage in SENT_STAGES and app.applied_date is None:
        app.applied_date = date.today()


def delete(db: Session, user_id: int, app_id: int) -> None:
    app = get_owned(db, user_id, app_id)
    db.delete(app)
    db.commit()


def add_interview(db: Session, user_id: int, app_id: int, data: dict) -> Interview:
    app = get_owned(db, user_id, app_id)
    interview = Interview(application_id=app.id, **data)
    db.add(interview)
    # Scheduling an interview means the company replied — move it along the pipeline.
    if app.stage in (Stage.WISHLIST, Stage.APPLIED):
        app.stage = Stage.INTERVIEW
        _apply_stage_rules(app, Stage.INTERVIEW)
    app.updated_at = datetime.now()  # adding an interview counts as a change
    db.commit()
    db.refresh(interview)
    return interview


def delete_interview(db: Session, user_id: int, interview_id: int) -> None:
    interview = db.get(Interview, interview_id)
    if interview is None or interview.application.user_id != user_id:
        raise NotFound("Interview not found.")
    db.delete(interview)
    db.commit()
