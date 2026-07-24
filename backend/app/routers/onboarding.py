from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.models.schemas import OnboardingRequest, OnboardingResponse
from app.services import onboarding_service

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


@router.post("", response_model=OnboardingResponse)
def submit_onboarding(
    payload: OnboardingRequest, db: Session = Depends(get_db)
) -> OnboardingResponse:
    """Единая форма: квартира + техника + тариф (см. MVP-скоуп в CLAUDE.md)."""
    return onboarding_service.create_profile(db, payload)
