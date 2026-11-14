from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Application, Interview, Stage

REPLIED_STAGES = {Stage.INTERVIEW, Stage.OFFER, Stage.REJECTED}


def week_bounds(today: date) -> tuple[date, date]:
    """Monday..Sunday of the week containing `today`."""
    start = today - timedelta(days=today.weekday())
    return start, start + timedelta(days=6)


def get_dashboard(db: Session, user_id: int, now: datetime | None = None) -> dict:
    now = now or datetime.now()
    week_start, week_end = week_bounds(now.date())

    counts = dict(db.execute(
        select(Application.stage, func.count()).where(Application.user_id == user_id)
        .group_by(Application.stage)
    ).all())
    by_stage = {s.value: counts.get(s.value, 0) for s in Stage}

    # Response rate = applications that got a reply / applications sent.
    # "Sent" = has an applied date or is past Wishlist (Rejected-from-Wishlist without a
    # date counts as never sent). "Reply" = reached Interview/Offer/Rejected or has an interview.
    apps = db.execute(
        select(Application.id, Application.stage, Application.applied_date)
        .where(Application.user_id == user_id)
    ).all()
    with_interviews = set(db.scalars(
        select(Interview.application_id).join(Application)
        .where(Application.user_id == user_id).distinct()
    ))
    sent = [a for a in apps if a.applied_date is not None or a.stage in (Stage.APPLIED, Stage.INTERVIEW, Stage.OFFER)]
    replied = [a for a in sent if a.stage in REPLIED_STAGES or a.id in with_interviews]
    response_rate = round(100 * len(replied) / len(sent), 1) if sent else None

    week_from = datetime.combine(week_start, datetime.min.time())
    week_to = week_from + timedelta(days=7)
    interviews_this_week = db.scalar(
        select(func.count(Interview.id)).join(Application)
        .where(Application.user_id == user_id,
               Interview.scheduled_at >= week_from, Interview.scheduled_at < week_to)
    ) or 0

    upcoming_rows = db.execute(
        select(Interview, Application.company, Application.role).join(Application)
        .where(Application.user_id == user_id, Interview.scheduled_at >= now)
        .order_by(Interview.scheduled_at).limit(5)
    ).all()
    upcoming = [
        {"id": i.id, "application_id": i.application_id, "company": c, "role": r,
         "scheduled_at": i.scheduled_at, "round": i.round}
        for i, c, r in upcoming_rows
    ]

    return {
        "total_applications": len(apps),
        "by_stage": by_stage,
        "interviews_this_week": interviews_this_week,
        "upcoming_interviews": upcoming,
        "applications_sent": len(sent),
        "applications_with_response": len(replied),
        "response_rate": response_rate,
        "week_start": week_start,
        "week_end": week_end,
    }
