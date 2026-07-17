"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getAnomalies, getForecast } from "@/lib/api";
import { getProfileId } from "@/lib/profile";
import type { AnomaliesResponse, ForecastResponse } from "@/lib/types";

export default function DashboardPage() {
  const [profileId] = useState<string | null>(() => getProfileId());
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
    return <p className="text-sm text-foreground/60">Загружаем прогноз...</p>;
  }

  const hasForecast =
    forecast.status === "ok" && forecast.predicted_amount_tenge !== null;

  return (
    <div className="flex flex-col gap-8">
      <div>
        <h1 className="text-2xl font-semibold">Дашборд</h1>
        <p className="text-sm text-foreground/60">
          {hasForecast
            ? `Прогноз на ${forecast.forecast_period}`
            : "Прогноз счёта"}
        </p>
      </div>

      {hasForecast ? (
        <div className="flex flex-col gap-1 rounded-lg border border-black/10 p-5 dark:border-white/10">
          <span className="text-sm text-foreground/60">Ожидаемая сумма счёта</span>
          <span className="text-3xl font-semibold">
            {forecast.predicted_amount_tenge!.toLocaleString("ru-RU")} ₸
          </span>
          {forecast.predicted_amount_lower_tenge !== null &&
            forecast.predicted_amount_upper_tenge !== null && (
              <span className="text-sm text-foreground/60">
                Вероятный диапазон:{" "}
                {forecast.predicted_amount_lower_tenge.toLocaleString("ru-RU")} –{" "}
                {forecast.predicted_amount_upper_tenge.toLocaleString("ru-RU")} ₸
              </span>
            )}
          <span className="text-sm text-foreground/60">
            {forecast.predicted_consumption_kwh ?? "—"} кВт·ч · по истории за{" "}
            {forecast.history_points} мес.
          </span>
        </div>
      ) : (
        <div className="flex flex-col gap-2 rounded-lg border border-amber-500/30 bg-amber-500/5 p-5">
          <span className="font-medium">Прогноз пока недоступен</span>
          <span className="text-sm text-foreground/70">
            {forecast.message ??
              "Недостаточно истории счетов для прогноза. Загрузите ещё счета."}
          </span>
        </div>
      )}

      {hasForecast && (
      <div className="flex flex-col gap-3">
        <h2 className="font-medium">Разбивка по категориям</h2>
        <div className="flex flex-col gap-2">
          {forecast.breakdown.map((category) => (
            <div key={category.category} className="flex flex-col gap-1">
              <div className="flex justify-between text-sm">
                <span>{category.category}</span>
                <span className="text-foreground/60">
                  {category.amount_tenge.toLocaleString("ru-RU")} ₸ ·{" "}
                  {category.share_percent}%
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
      )}

      <div className="flex flex-col gap-3">
        <h2 className="font-medium">Аномалии</h2>
        {anomalies.anomalies.length === 0 ? (
          <p className="text-sm text-foreground/60">Аномалий не обнаружено.</p>
        ) : (
          anomalies.anomalies.map((anomaly) => (
            <div
              key={anomaly.id}
              className="flex flex-col gap-1 rounded-lg border border-amber-500/30 bg-amber-500/5 p-4"
            >
              <div className="flex items-center justify-between">
                <span className="font-medium">{anomaly.title}</span>
                <span className="text-xs uppercase text-amber-700 dark:text-amber-400">
                  {anomaly.severity}
                </span>
              </div>
              <p className="text-sm text-foreground/70">{anomaly.description}</p>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
