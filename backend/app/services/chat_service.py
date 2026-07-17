"""Заглушка сервиса чата-энергокоуча.

Контракт ответа уже содержит `sources` — какие данные (профиль/прогноз/
тариф/погода) учтены. Это заранее закладывает structured pipeline из
CLAUDE.md (не голый chat-wrapper над LLM API), даже пока сам pipeline
не реализован.
"""

from app.models.schemas import ChatMessageRequest, ChatMessageResponse


def get_coach_reply(payload: ChatMessageRequest) -> ChatMessageResponse:
    return ChatMessageResponse(
        reply=(
            "Мок-ответ энергокоуча: судя по профилю квартиры, основной расход даёт "
            "бойлер. Попробуйте сократить время работы на 1 час в сутки."
        ),
        estimated_savings_tenge=1200.0,
        sources=["profile", "forecast", "tariff"],
    )
