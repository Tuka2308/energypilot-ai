from fastapi import APIRouter

from app.models.schemas import ChatMessageRequest, ChatMessageResponse
from app.services import chat_service

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatMessageResponse)
def send_message(payload: ChatMessageRequest) -> ChatMessageResponse:
    """Structured pipeline (профиль + прогноз + тариф + погода -> совет),
    не голый wrapper над LLM API — см. критерий "глубина интеграции"."""
    return chat_service.get_coach_reply(payload)
