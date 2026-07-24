from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.models.schemas import ChatMessageRequest, ChatMessageResponse
from app.services import chat_service

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatMessageResponse)
def send_message(
    payload: ChatMessageRequest, db: Session = Depends(get_db)
) -> ChatMessageResponse:
    """Structured pipeline (профиль + прогноз + тариф + аномалии -> совет),
    не голый wrapper над LLM API — см. критерий "глубина интеграции"."""
    return chat_service.get_coach_reply(db, payload)
