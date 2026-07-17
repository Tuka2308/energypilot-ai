"""AI-чат «энергокоуч» — structured pipeline, НЕ голый chat-wrapper.

Пайплайн по шагам (этот блок — шпаргалка для Q&A, каждый шаг виден в коде):

1. СБОР КОНТЕКСТА (`build_context`). По profile_id тянем данные из ТЕХ ЖЕ
   сервисов, что кормят дашборд: профиль квартиры/техники/тарифа
   (onboarding_service), прогноз Prophet с интервалом или статусом
   insufficient_history (forecast_service), аномалии порогового правила со
   структурированными полями metric/current/baseline (anomalies_service).
   У чата нет собственной аналитики — он потребитель фактов, поэтому его
   ответы не могут разойтись с цифрами на дашборде.

2. БЛОК ФАКТОВ (`_render_facts`). Контекст рендерится в явный текстовый
   блок с секциями КВАРТИРА/ТЕХНИКА/ТАРИФ/ПРОГНОЗ/АНОМАЛИИ. Ключевой
   момент: если прогноза нет (insufficient_history), в блоке это сказано
   прямым запретом («прогноза НЕТ — не называй сумму»), а не просто
   пропуском секции — LLM не должна дофантазировать число.

3. ПРАВИЛА (`SYSTEM_RULES`). Системный промпт требует: советы только из
   блока фактов, каждая рекомендация — с оценкой экономии и с показанным
   расчётом («бойлер 2 кВт ~3ч/день ≈ 180 кВт·ч × 22 ₸ ...»), запрет на
   выдуманные числа, краткость, русский язык.

4. ПАМЯТЬ ДИАЛОГА (`_sessions`). История сообщений сессии хранится
   in-memory по profile_id (как профили/история счетов — БД следующий
   шаг). Уточняющий вопрос («а если стирать ночью?») уходит в LLM вместе
   с предыдущими репликами, обрезанными до MAX_TURNS последних пар.

5. ВЫЗОВ LLM (`_call_llm`). Каскад провайдеров, первый настроенный и
   рабочий побеждает: Gemini (JSON-mode, gemini-2.0-flash — бесплатный
   ключ команды) → OpenAI (тот же JSON-контракт {reply,
   estimated_savings_tenge}) → Ollama офлайн → детерминированный
   офлайн-fallback из собранного контекста с явной пометкой, как включить
   LLM. Ни один сбой одного провайдера не роняет эндпоинт — просто пробуем
   следующий по каскаду.

6. ОТВЕТ. ChatMessageResponse.sources перечисляет, какие блоки данных
   реально вошли в контекст («profile», «forecast», «anomalies»,
   «tariff») — фронт/жюри видят, из чего собран ответ.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from app.core.config import settings
from app.models.schemas import (
    AnomaliesResponse,
    AnomalyStatus,
    ChatMessageRequest,
    ChatMessageResponse,
    ForecastResponse,
    ForecastStatus,
    OnboardingRequest,
)
from app.services import anomalies_service, forecast_service, onboarding_service

logger = logging.getLogger(__name__)

# Пар «вопрос-ответ» в памяти диалога. Больше не нужно: контекст фактов
# передаётся каждый раз заново, история нужна только для уточняющих вопросов.
MAX_TURNS = 8

_sessions: dict[str, list[dict[str, str]]] = {}


class LLMUnavailable(RuntimeError):
    """Ни один LLM-бэкенд не настроен/не ответил — уходим в офлайн-fallback."""


# --- Шаг 1-2: сбор контекста и блок фактов -----------------------------------


@dataclass
class CoachContext:
    profile: OnboardingRequest | None
    forecast: ForecastResponse
    anomalies: AnomaliesResponse


def build_context(profile_id: str) -> CoachContext:
    return CoachContext(
        profile=onboarding_service.get_profile(profile_id),
        forecast=forecast_service.get_forecast(profile_id),
        anomalies=anomalies_service.get_anomalies(profile_id),
    )


def _render_facts(ctx: CoachContext) -> str:
    lines: list[str] = ["ДАННЫЕ ПОЛЬЗОВАТЕЛЯ (единственный источник фактов):"]

    if ctx.profile:
        p = ctx.profile
        lines.append(
            f"КВАРТИРА: {p.city}, {p.area_sqm:g} м², жильцов: {p.occupants}."
        )
        if p.appliances:
            appliances = ", ".join(
                f"{a.name}"
                + (f" {a.power_watts} Вт" if a.power_watts else "")
                + (f" ×{a.quantity}" if a.quantity > 1 else "")
                for a in p.appliances
            )
            lines.append(f"ТЕХНИКА: {appliances}.")
        tariff = {
            "flat": "единый",
            "differentiated": "дифференцированный (день/ночь — ночью дешевле)",
            "stepped": "ступенчатый по объёму (превышение ступени дороже)",
        }[p.tariff_type.value]
        rate = f", ставка {p.tariff_rate:g} ₸/кВт·ч" if p.tariff_rate else ""
        lines.append(f"ТАРИФ: {tariff}{rate}.")
    else:
        lines.append("КВАРТИРА/ТЕХНИКА/ТАРИФ: анкета не заполнена.")

    f = ctx.forecast
    if f.status == ForecastStatus.ok and f.predicted_amount_tenge is not None:
        lines.append(
            f"ПРОГНОЗ на {f.forecast_period}: {f.predicted_amount_tenge:g} ₸ "
            f"(диапазон {f.predicted_amount_lower_tenge:g}–{f.predicted_amount_upper_tenge:g} ₸)"
            + (
                f", ~{f.predicted_consumption_kwh:g} кВт·ч"
                if f.predicted_consumption_kwh
                else ""
            )
            + f"; построен по истории за {f.history_points} мес."
        )
    else:
        # Явный запрет вместо молчаливого пропуска секции — иначе LLM
        # склонна «услужливо» назвать правдоподобную сумму.
        lines.append(
            f"ПРОГНОЗ: НЕДОСТУПЕН (истории всего {f.history_points} мес.). "
            "ЗАПРЕЩЕНО называть сумму прогноза или выдумывать её — вместо "
            "этого предложи загрузить ещё счета."
        )

    a = ctx.anomalies
    if a.status == AnomalyStatus.ok and a.anomalies:
        for an in a.anomalies:
            unit = "кВт·ч" if an.metric == "consumption_kwh" else "₸"
            lines.append(
                f"АНОМАЛИЯ за {an.current_period}: {an.current_value:g} {unit} "
                f"против {an.baseline_value:g} {unit} ({an.baseline_label}) — "
                f"рост +{an.change_percent:g}%, серьёзность {an.severity.value}."
            )
    elif a.status == AnomalyStatus.ok:
        lines.append("АНОМАЛИИ: не обнаружены, расход в норме.")
    else:
        lines.append("АНОМАЛИИ: проверка недоступна (мало истории).")

    return "\n".join(lines)


def _sources(ctx: CoachContext) -> list[str]:
    sources = []
    if ctx.profile:
        sources.append("profile")
        if ctx.profile.tariff_rate or ctx.profile.tariff_type:
            sources.append("tariff")
    if ctx.forecast.status == ForecastStatus.ok:
        sources.append("forecast")
    if ctx.anomalies.status == AnomalyStatus.ok and ctx.anomalies.anomalies:
        sources.append("anomalies")
    return sources


# --- Шаг 3: правила для LLM ---------------------------------------------------

SYSTEM_RULES = """Ты — энергокоуч EnergyPilot AI: помогаешь семье в Казахстане снизить счёт за электричество без потери комфорта.

ПРАВИЛА:
1. Используй ТОЛЬКО факты из блока «ДАННЫЕ ПОЛЬЗОВАТЕЛЯ» ниже. Не выдумывай числа, приборы и тарифы, которых там нет.
2. Каждая рекомендация — конкретная и персональная (привязана к технике/тарифу/аномалии пользователя), с оценкой экономии в тенге или процентах И с коротким показанным расчётом. Пример формата: «Перенесите стирку на ночь: при дифференцированном тарифе это ≈ −8% от счёта (стиральная машина ~2 кВт·ч/цикл × 20 циклов × разница тарифа)».
3. Если в данных есть аномалия — начни с неё: объясни её цифры простыми словами и что проверить в первую очередь.
4. Если прогноз недоступен — честно скажи об этом и предложи загрузить счета за прошлые месяцы; НЕ называй сумму.
5. Отвечай по-русски, кратко (до ~150 слов), без воды и без общих советов вида «выключайте свет».

ФОРМАТ ОТВЕТА — строго JSON без markdown:
{"reply": "<текст ответа>", "estimated_savings_tenge": <число ₸/мес или null, только если экономия реально посчитана из данных>}"""


# --- Шаг 5: каскад LLM-бэкендов ----------------------------------------------


def _call_llm(system_prompt: str, messages: list[dict[str, str]]) -> tuple[str, float | None]:
    if settings.gemini_api_key:
        try:
            return _call_gemini(system_prompt, messages)
        except Exception:
            logger.warning("Gemini недоступен, пробуем OpenAI", exc_info=True)
    if settings.openai_api_key:
        try:
            return _call_openai(system_prompt, messages)
        except Exception:
            logger.warning("OpenAI недоступен, пробуем Ollama", exc_info=True)
    if settings.ollama_base_url:
        try:
            return _call_ollama(system_prompt, messages)
        except Exception:
            logger.warning("Ollama недоступен", exc_info=True)
    raise LLMUnavailable


def _call_gemini(system_prompt: str, messages: list[dict[str, str]]) -> tuple[str, float | None]:
    # Ленивый импорт: без ключа SDK не нужен (см. комментарий у _call_openai).
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.gemini_api_key)
    # Gemini использует роль "model" вместо "assistant" — единственная
    # разница в контракте messages по сравнению с OpenAI/Ollama.
    contents = [
        types.Content(
            role="model" if m["role"] == "assistant" else "user",
            parts=[types.Part(text=m["content"])],
        )
        for m in messages
    ]
    response = client.models.generate_content(
        model=settings.gemini_model,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",  # тот же JSON-контракт, что у OpenAI
            temperature=0.4,
        ),
    )
    return _parse_llm_json(response.text or "")


def _call_openai(system_prompt: str, messages: list[dict[str, str]]) -> tuple[str, float | None]:
    # Ленивый импорт: без ключа SDK не нужен, и его отсутствие не должно
    # ронять импорт модуля.
    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)
    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=[{"role": "system", "content": system_prompt}, *messages],
        response_format={"type": "json_object"},  # структурированный ответ
        temperature=0.4,  # советы должны быть стабильными, не «креативными»
    )
    return _parse_llm_json(response.choices[0].message.content or "")


def _call_ollama(system_prompt: str, messages: list[dict[str, str]]) -> tuple[str, float | None]:
    # stdlib urllib вместо лишней зависимости: один POST-запрос.
    import urllib.request

    payload = json.dumps(
        {
            "model": settings.ollama_model,
            "messages": [{"role": "system", "content": system_prompt}, *messages],
            "format": "json",
            "stream": False,
        }
    ).encode()
    request = urllib.request.Request(
        f"{settings.ollama_base_url.rstrip('/')}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=60) as raw:
        body = json.loads(raw.read())
    return _parse_llm_json(body.get("message", {}).get("content", ""))


def _parse_llm_json(content: str) -> tuple[str, float | None]:
    """Достаём {reply, estimated_savings_tenge}; если модель нарушила формат —
    отдаём сырой текст как ответ, а не падаем."""
    try:
        data = json.loads(content)
        reply = str(data.get("reply", "")).strip() or content
        savings = data.get("estimated_savings_tenge")
        return reply, float(savings) if isinstance(savings, (int, float)) else None
    except (json.JSONDecodeError, TypeError):
        return content.strip(), None


# --- Шаг 5б: офлайн-fallback --------------------------------------------------

_OFFLINE_NOTE = (
    "\n\n⚙️ Офлайн-режим: LLM не настроен. Для полноценных ответов добавьте "
    "GEMINI_API_KEY (или OPENAI_API_KEY / OLLAMA_BASE_URL) в backend/.env "
    "— см. backend/README.md."
)


def _fallback_reply(ctx: CoachContext) -> tuple[str, float | None]:
    """Детерминированный ответ из того же контекста, что ушёл бы в LLM:
    демо работает без сети/ключей, но честно помечено как офлайн-режим."""
    parts: list[str] = []
    savings: float | None = None
    f, a = ctx.forecast, ctx.anomalies

    if a.status == AnomalyStatus.ok and a.anomalies:
        an = a.anomalies[0]
        unit = "кВт·ч" if an.metric == "consumption_kwh" else "₸"
        parts.append(
            f"Главное сейчас: {an.title.lower()} — {an.current_value:g} {unit} против "
            f"{an.baseline_value:g} {unit} ({an.baseline_label}). Проверьте, не появился "
            f"ли новый прибор и не изменился ли режим (бойлер, обогреватель)."
        )
        if f.status == ForecastStatus.ok and f.predicted_amount_tenge and an.current_value:
            excess_share = (an.current_value - an.baseline_value) / an.current_value
            savings = round(f.predicted_amount_tenge * excess_share)
            parts.append(
                f"Вернув расход к прежней базе, вы сэкономите ≈ {savings:g} ₸ от "
                f"прогнозных {f.predicted_amount_tenge:g} ₸ "
                f"(доля превышения {excess_share:.0%} × прогноз)."
            )
    elif f.status == ForecastStatus.ok and f.predicted_amount_tenge:
        parts.append(
            f"Прогноз на {f.forecast_period}: ≈ {f.predicted_amount_tenge:g} ₸ "
            f"(диапазон {f.predicted_amount_lower_tenge:g}–{f.predicted_amount_upper_tenge:g} ₸). "
            f"Аномалий нет — расход в вашей норме."
        )
    else:
        parts.append(
            "Пока недостаточно истории счетов для прогноза и проверки аномалий "
            f"(есть {f.history_points} мес.). Загрузите счета за прошлые месяцы "
            "на странице «Загрузка счёта» — после этого советы станут предметными."
        )

    if ctx.profile and ctx.profile.tariff_type.value == "differentiated" and ctx.profile.appliances:
        heavy = max(ctx.profile.appliances, key=lambda x: x.power_watts or 0)
        if heavy.power_watts:
            parts.append(
                f"У вас тариф день/ночь и «{heavy.name}» на {heavy.power_watts} Вт — "
                f"перенос его работы на ночные часы даёт типовую экономию до ~8% счёта."
            )

    return " ".join(parts) + _OFFLINE_NOTE, savings


# --- Шаги 4+6: публичная точка входа -----------------------------------------


def get_coach_reply(payload: ChatMessageRequest) -> ChatMessageResponse:
    ctx = build_context(payload.profile_id)
    system_prompt = SYSTEM_RULES + "\n\n" + _render_facts(ctx)

    history = _sessions.setdefault(payload.profile_id, [])
    messages = [*history, {"role": "user", "content": payload.message}]

    try:
        reply, savings = _call_llm(system_prompt, messages)
    except LLMUnavailable:
        reply, savings = _fallback_reply(ctx)

    # Память диалога: пишем пару после ответа, держим последние MAX_TURNS пар.
    history.append({"role": "user", "content": payload.message})
    history.append({"role": "assistant", "content": reply})
    del history[: -2 * MAX_TURNS]

    return ChatMessageResponse(
        reply=reply,
        estimated_savings_tenge=savings,
        sources=_sources(ctx),
    )


def clear_sessions(profile_id: str | None = None) -> None:
    """Сброс памяти диалога — для тестов."""
    if profile_id is None:
        _sessions.clear()
    else:
        _sessions.pop(profile_id, None)
