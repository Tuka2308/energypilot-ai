"use client";

// Единый дашборд — финальный экран демо. Собирает прогноз, аномалии и
// переход к энергокоучу в одну связную картину: прогноз (сколько будет) →
// аномалия (что не так) → CTA в чат (что с этим делать). Вопрос для коуча
// формируется из тех же данных, что показаны на экране, — судья видит, что
// блоки связаны, а не живут порознь.

import { useEffect, useState } from "react";
import Link from "next/link";
import { getAnomalies, getForecast } from "@/lib/api";
import { useProfileId } from "@/lib/profile";
import type {
  AnomaliesResponse,
  Anomaly,
  ForecastResponse,
} from "@/lib/types";

// Зеркалит MIN_HISTORY_POINTS бэкенда — для прогресс-бара «N из 3 месяцев».
const MIN_HISTORY_MONTHS = 3;

export default function DashboardPage() {
  const profileId = useProfileId();
  const [forecast, setForecast] = useState<ForecastResponse | null>(null);
  const [anomalies, setAnomalies] = useState<AnomaliesResponse | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");

  useEffect(() => {
    if (!profileId) return;
    Promise.all([getForecast(profileId), getAnomalies(profileId)])
      .then(([forecastData, anomaliesData]) => {
        setForecast(forecastData);
        setAnomalies(anomaliesData);
        setStatus("ready");
      })
      .catch(() => setStatus("error"));
  }, [profileId]);

  // undefined = гидрация ещё идёт: рендерим тот же плейсхолдер, что отдал
  // сервер, — иначе hydration mismatch (см. useProfileId).
  if (profileId === undefined) {
    return <p className="text-sm text-foreground/60">Собираем сводку...</p>;
  }

  if (!profileId) {
    return (
      <div className="flex flex-col gap-3">
        <h1 className="text-2xl font-semibold">Дашборд</h1>
        <p className="text-sm text-foreground/60">
          Сначала заполните{" "}
          <Link href="/onboarding" className="underline">
            анкету квартиры
          </Link>
          .
        </p>
      </div>
    );
  }

  if (status === "error") {
    return (
      <p className="text-sm text-red-600">
        Не удалось загрузить данные. Проверьте, что backend запущен.
      </p>
    );
  }

  if (status === "loading" || !forecast || !anomalies) {
    return <p className="text-sm text-foreground/60">Собираем сводку...</p>;
  }

  const hasForecast =
    forecast.status === "ok" && forecast.predicted_amount_tenge !== null;
  const anomaly: Anomaly | null =
    anomalies.status === "ok" && anomalies.anomalies.length > 0
      ? anomalies.anomalies[0]
      : null;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Дашборд</h1>
          <p className="text-sm text-foreground/60">
            {hasForecast
              ? `Сводка по счёту на ${forecast.forecast_period}`
              : "Сводка по вашему счёту"}
          </p>
        </div>
        {hasForecast && (
          <span className="text-xs text-foreground/50">
            история: {forecast.history_points} мес.
          </span>
        )}
      </div>

      {hasForecast ? (
        <ForecastHero forecast={forecast} anomaly={anomaly} />
      ) : (
        <HistoryProgressHero
          points={forecast.history_points}
          message={forecast.message}
        />
      )}

      {hasForecast && (
        <div className="grid gap-6 sm:grid-cols-2">
          <BreakdownCard forecast={forecast} />
          <AnomalyCard anomalies={anomalies} anomaly={anomaly} />
        </div>
      )}

      <CoachCta forecast={forecast} anomaly={anomaly} hasForecast={hasForecast} />
    </div>
  );
}

// --- Прогноз: сумма + визуальный диапазон -----------------------------------

function ForecastHero({
  forecast,
  anomaly,
}: {
  forecast: ForecastResponse;
  anomaly: Anomaly | null;
}) {
  const predicted = forecast.predicted_amount_tenge!;
  const lower = forecast.predicted_amount_lower_tenge;
  const upper = forecast.predicted_amount_upper_tenge;
  // Позиция маркера прогноза внутри полосы диапазона (0–100%).
  const markerPercent =
    lower !== null && upper !== null && upper > lower
      ? Math.min(100, Math.max(0, ((predicted - lower) / (upper - lower)) * 100))
      : 50;

  return (
    <div className="flex flex-col gap-4 rounded-xl border border-black/10 p-6 dark:border-white/10">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div className="flex flex-col gap-1">
          <span className="text-sm text-foreground/60">
            Ожидаемая сумма счёта
          </span>
          <span className="text-4xl font-semibold tracking-tight">
            {predicted.toLocaleString("ru-RU")} ₸
          </span>
        </div>
        <div className="flex flex-col items-end gap-1 text-sm text-foreground/60">
          <span>{forecast.predicted_consumption_kwh ?? "—"} кВт·ч</span>
          {anomaly && (
            <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-xs font-medium text-amber-700 dark:text-amber-400">
              учтён рост +{Math.round(anomaly.change_percent)}%
            </span>
          )}
        </div>
      </div>

      {lower !== null && upper !== null && (
        <div className="flex flex-col gap-1.5">
          <div className="relative h-2.5 w-full rounded-full bg-black/10 dark:bg-white/10">
            <div
              className="absolute top-1/2 h-4 w-1 -translate-y-1/2 rounded-full bg-foreground"
              style={{ left: `calc(${markerPercent}% - 2px)` }}
              aria-hidden
            />
          </div>
          <div className="flex justify-between text-xs text-foreground/50">
            <span>от {lower.toLocaleString("ru-RU")} ₸</span>
            <span>вероятный диапазон</span>
            <span>до {upper.toLocaleString("ru-RU")} ₸</span>
          </div>
        </div>
      )}
    </div>
  );
}

// --- Нет истории: прогресс, а не ошибка --------------------------------------

function HistoryProgressHero({
  points,
  message,
}: {
  points: number;
  message: string | null;
}) {
  return (
    <div className="flex flex-col gap-4 rounded-xl border border-black/10 p-6 dark:border-white/10">
      <div className="flex flex-col gap-1">
        <span className="font-medium">Копим историю для прогноза</span>
        <span className="text-sm text-foreground/60">
          {message ??
            "Прогноз и проверка аномалий появятся после нескольких загруженных счетов."}
        </span>
      </div>

      <div className="flex items-center gap-3">
        <div className="flex gap-1.5">
          {Array.from({ length: MIN_HISTORY_MONTHS }).map((_, i) => (
            <div
              key={i}
              className={`h-2.5 w-8 rounded-full ${
                i < points
                  ? "bg-foreground"
                  : "bg-black/10 dark:bg-white/10"
              }`}
            />
          ))}
        </div>
        <span className="text-sm text-foreground/60">
          {points} из {MIN_HISTORY_MONTHS} мес.
        </span>
      </div>

      <Link
        href="/bills"
        className="w-fit rounded-full bg-foreground px-5 py-2 text-sm font-medium text-background transition-colors hover:bg-foreground/85"
      >
        Загрузить счёт
      </Link>
    </div>
  );
}

// --- Разбивка по категориям ---------------------------------------------------

function BreakdownCard({ forecast }: { forecast: ForecastResponse }) {
  return (
    <div className="flex flex-col gap-3 rounded-xl border border-black/10 p-5 dark:border-white/10">
      <h2 className="font-medium">Из чего складывается</h2>
      <div className="flex flex-col gap-2">
        {forecast.breakdown.map((category) => (
          <div key={category.category} className="flex flex-col gap-1">
            <div className="flex justify-between text-sm">
              <span>{category.category}</span>
              <span className="text-foreground/60">
                {category.amount_tenge.toLocaleString("ru-RU")} ₸
              </span>
            </div>
            <div className="h-2 w-full rounded-full bg-black/10 dark:bg-white/10">
              <div
                className="h-2 rounded-full bg-foreground"
                style={{ width: `${category.share_percent}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// --- Аномалии: всегда осмысленное состояние ----------------------------------

function AnomalyCard({
  anomalies,
  anomaly,
}: {
  anomalies: AnomaliesResponse;
  anomaly: Anomaly | null;
}) {
  if (anomalies.status === "insufficient_history") {
    return (
      <div className="flex flex-col gap-2 rounded-xl border border-black/10 p-5 dark:border-white/10">
        <h2 className="font-medium">Контроль аномалий</h2>
        <p className="text-sm text-foreground/60">
          Включится, когда накопится история — сравнивать текущий месяц пока
          не с чем.
        </p>
      </div>
    );
  }

  if (!anomaly) {
    return (
      <div className="flex flex-col gap-2 rounded-xl border border-emerald-500/25 bg-emerald-500/5 p-5">
        <h2 className="font-medium">Расход в норме</h2>
        <p className="text-sm text-foreground/70">
          Потребление в пределах вашей обычной картины — резких скачков не
          обнаружено.
        </p>
      </div>
    );
  }

  const unit = anomaly.metric === "consumption_kwh" ? "кВт·ч" : "₸";
  return (
    <div className="flex flex-col gap-2 rounded-xl border border-amber-500/30 bg-amber-500/5 p-5">
      <div className="flex items-center justify-between gap-2">
        <h2 className="font-medium">{anomaly.title}</h2>
        <span className="shrink-0 rounded-full bg-amber-500/15 px-2 py-0.5 text-xs font-medium uppercase text-amber-700 dark:text-amber-400">
          {anomaly.severity}
        </span>
      </div>
      {anomaly.current_value !== null && anomaly.baseline_value !== null && (
        <div className="flex items-baseline gap-2 text-sm">
          <span className="text-lg font-semibold">
            {anomaly.current_value.toLocaleString("ru-RU")} {unit}
          </span>
          <span className="text-foreground/50">
            против {anomaly.baseline_value.toLocaleString("ru-RU")} {unit} (
            {anomaly.baseline_label})
          </span>
        </div>
      )}
      <p className="text-sm text-foreground/70">{anomaly.description}</p>
    </div>
  );
}

// --- CTA в чат: вопрос собран из данных на экране ----------------------------

function CoachCta({
  forecast,
  anomaly,
  hasForecast,
}: {
  forecast: ForecastResponse;
  anomaly: Anomaly | null;
  hasForecast: boolean;
}) {
  // Контекстный вопрос: тот же, что пользователь видит на экране, — чат
  // откроется уже с ним (см. ?q= в chat/page.tsx).
  const question = anomaly
    ? `Почему расход вырос на ${Math.round(anomaly.change_percent)}% за ${anomaly.current_period} и как вернуть его к норме?`
    : hasForecast
      ? `Прогноз на ${forecast.forecast_period} — ${forecast.predicted_amount_tenge!.toLocaleString("ru-RU")} ₸. Как его снизить?`
      : "С чего начать экономию, пока копится история счетов?";

  return (
    <Link
      href={`/chat?q=${encodeURIComponent(question)}`}
      className="group flex items-center justify-between gap-4 rounded-xl border border-black/10 bg-black/[.03] p-5 transition-colors hover:border-black/25 dark:border-white/10 dark:bg-white/[.04] dark:hover:border-white/25"
    >
      <div className="flex flex-col gap-1">
        <span className="text-sm text-foreground/60">
          {anomaly ? "Спросить энергокоуча про этот скачок" : "Спросить энергокоуча"}
        </span>
        <span className="font-medium">«{question}»</span>
      </div>
      <span className="shrink-0 rounded-full bg-foreground px-5 py-2 text-sm font-medium text-background transition-colors group-hover:bg-foreground/85">
        В чат →
      </span>
    </Link>
  );
}
