"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { submitManualCorrection, uploadBill } from "@/lib/api";
import { useProfileId } from "@/lib/profile";
import type { BillUploadResponse } from "@/lib/types";

export default function BillsPage() {
  const router = useRouter();
  const profileId = useProfileId();
  const [uploadStatus, setUploadStatus] = useState<"idle" | "uploading" | "error">("idle");
  const [ocrResult, setOcrResult] = useState<BillUploadResponse | null>(null);
  const [amount, setAmount] = useState<number | undefined>();
  const [consumption, setConsumption] = useState<number | undefined>();
  const [period, setPeriod] = useState("");
  const [saved, setSaved] = useState(false);

  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploadStatus("uploading");
    try {
      // OCR никогда не должен блокировать флоу: даже если распознавание
      // низкой уверенности, показываем то, что есть, и даём поправить руками.
      const result = await uploadBill(file, profileId);
      setOcrResult(result);
      setAmount(result.amount_tenge ?? undefined);
      setConsumption(result.consumption_kwh ?? undefined);
      setPeriod(result.period ?? "");
      setUploadStatus("idle");
    } catch {
      setUploadStatus("error");
    }
  }

  async function handleConfirm(e: React.FormEvent) {
    e.preventDefault();
    if (!ocrResult || amount === undefined || !period) return;
    await submitManualCorrection({
      bill_id: ocrResult.bill_id,
      amount_tenge: amount,
      consumption_kwh: consumption,
      period,
      profile_id: profileId,
    });
    setSaved(true);
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold">Загрузка счёта</h1>
        <p className="text-sm text-foreground/60">
          Фото или PDF квитанции. Распознавание может ошибиться — всегда
          можно поправить сумму и показания вручную.
        </p>
      </div>

      <label className="flex w-fit cursor-pointer flex-col gap-2 rounded-lg border border-dashed border-black/20 px-6 py-8 text-sm dark:border-white/20">
        {uploadStatus === "uploading" ? "Распознаём..." : "Выбрать файл счёта (фото / PDF)"}
        <input
          type="file"
          accept="image/*,application/pdf"
          className="hidden"
          onChange={handleFileChange}
        />
      </label>

      {uploadStatus === "error" && (
        <p className="text-sm text-red-600">
          Не удалось загрузить файл. Проверьте, что backend запущен, и попробуйте снова.
        </p>
      )}

      {ocrResult && (
        <form onSubmit={handleConfirm} className="flex max-w-md flex-col gap-4">
          <p className="text-sm text-foreground/60">
            Статус распознавания: <span className="font-mono">{ocrResult.ocr_status}</span>
            {ocrResult.requires_manual_review && " — проверьте данные ниже"}
          </p>

          <label className="flex flex-col gap-1 text-sm">
            Период (например, 2026-06)
            <input
              className="rounded border border-black/15 px-3 py-2 dark:border-white/15"
              value={period}
              onChange={(e) => setPeriod(e.target.value)}
              required
            />
          </label>

          <label className="flex flex-col gap-1 text-sm">
            Сумма, тенге
            <input
              type="number"
              min={0}
              className="rounded border border-black/15 px-3 py-2 dark:border-white/15"
              value={amount ?? ""}
              onChange={(e) => setAmount(Number(e.target.value))}
              required
            />
          </label>

          <label className="flex flex-col gap-1 text-sm">
            Потребление, кВт·ч (если указано в счёте)
            <input
              type="number"
              min={0}
              className="rounded border border-black/15 px-3 py-2 dark:border-white/15"
              value={consumption ?? ""}
              onChange={(e) => setConsumption(Number(e.target.value))}
            />
          </label>

          <div className="flex items-center gap-4">
            <button
              type="submit"
              className="self-start rounded-full bg-foreground px-6 py-2.5 text-sm font-medium text-background transition-colors hover:bg-foreground/85"
            >
              Подтвердить данные
            </button>
            {saved && (
              <button
                type="button"
                onClick={() => router.push("/dashboard")}
                className="text-sm font-medium text-foreground/80 hover:text-foreground"
              >
                Сохранено → к дашборду
              </button>
            )}
          </div>
        </form>
      )}
    </div>
  );
}
