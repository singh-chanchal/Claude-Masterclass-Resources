from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.ai.client import AIClient
from app.database import get_db
from app.deps import get_ai, get_current_user
from app.models import User
from app.schemas import ApplicationOut, MatchIn, MatchOut, SaveMatchIn
from app.services import match_service

router = APIRouter(prefix="/api/matches", tags=["matches"])


@router.post("", response_model=MatchOut, status_code=status.HTTP_201_CREATED)
def create_match(body: MatchIn, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db), ai: AIClient = Depends(get_ai)):
    return match_service.run_match(db, ai, user.id, body.job_description)


@router.get("", response_model=list[MatchOut])
def list_matches(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return match_service.list_matches(db, user.id)


@router.post("/{match_id}/save", response_model=ApplicationOut, status_code=status.HTTP_201_CREATED)
def save_match(match_id: int, body: SaveMatchIn, user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    return match_service.save_as_application(
        db, user.id, match_id, body.company, body.role, body.job_url, body.notes
    )
