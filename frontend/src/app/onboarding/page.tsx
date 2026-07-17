"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { submitOnboarding } from "@/lib/api";
import { saveProfileId } from "@/lib/profile";
import type { Appliance, TariffType } from "@/lib/types";

const TARIFF_OPTIONS: { value: TariffType; label: string }[] = [
  { value: "flat", label: "Единый тариф" },
  { value: "differentiated", label: "Дифференцированный (день/ночь)" },
  { value: "stepped", label: "Ступенчатый по объёму" },
];

const EMPTY_APPLIANCE: Appliance = { name: "", power_watts: undefined, quantity: 1 };

export default function OnboardingPage() {
  const router = useRouter();
  const [city, setCity] = useState("Караганда");
  const [areaSqm, setAreaSqm] = useState(55);
  const [occupants, setOccupants] = useState(3);
  const [tariffType, setTariffType] = useState<TariffType>("differentiated");
  const [tariffRate, setTariffRate] = useState<number | undefined>(undefined);
  const [appliances, setAppliances] = useState<Appliance[]>([
    { name: "Бойлер", power_watts: 2000, quantity: 1 },
  ]);
  const [status, setStatus] = useState<"idle" | "submitting" | "error">("idle");

  function updateAppliance(index: number, patch: Partial<Appliance>) {
    setAppliances((prev) =>
      prev.map((item, i) => (i === index ? { ...item, ...patch } : item)),
    );
  }

  function addAppliance() {
    setAppliances((prev) => [...prev, { ...EMPTY_APPLIANCE }]);
  }

  function removeAppliance(index: number) {
    setAppliances((prev) => prev.filter((_, i) => i !== index));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setStatus("submitting");
    try {
      const response = await submitOnboarding({
        city,
        area_sqm: areaSqm,
        occupants,
        tariff_type: tariffType,
        tariff_rate: tariffRate,
        appliances: appliances.filter((a) => a.name.trim() !== ""),
      });
      saveProfileId(response.profile_id);
      router.push("/bills");
    } catch {
      setStatus("error");
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold">Анкета квартиры</h1>
        <p className="text-sm text-foreground/60">
          Одна форма: квартира, техника и тариф — используется для прогноза и
          рекомендаций.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="flex flex-col gap-8">
        <fieldset className="flex flex-col gap-4">
          <legend className="mb-1 font-medium">Квартира</legend>

          <label className="flex flex-col gap-1 text-sm">
            Город
            <input
              className="rounded border border-black/15 px-3 py-2 dark:border-white/15"
              value={city}
              onChange={(e) => setCity(e.target.value)}
              required
            />
          </label>

          <div className="flex gap-4">
            <label className="flex flex-1 flex-col gap-1 text-sm">
              Площадь, м²
              <input
                type="number"
                min={1}
                className="rounded border border-black/15 px-3 py-2 dark:border-white/15"
                value={areaSqm}
                onChange={(e) => setAreaSqm(Number(e.target.value))}
                required
              />
            </label>
            <label className="flex flex-1 flex-col gap-1 text-sm">
              Жильцов
              <input
                type="number"
                min={1}
                className="rounded border border-black/15 px-3 py-2 dark:border-white/15"
                value={occupants}
                onChange={(e) => setOccupants(Number(e.target.value))}
                required
              />
            </label>
          </div>
        </fieldset>

        <fieldset className="flex flex-col gap-4">
          <legend className="mb-1 font-medium">Тариф</legend>
          <div className="flex gap-4">
            <label className="flex flex-1 flex-col gap-1 text-sm">
              Тип тарифа
              <select
                className="rounded border border-black/15 px-3 py-2 dark:border-white/15"
                value={tariffType}
                onChange={(e) => setTariffType(e.target.value as TariffType)}
              >
                {TARIFF_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-1 flex-col gap-1 text-sm">
              Ставка, тенге/кВт·ч (если известна)
              <input
                type="number"
                min={0}
                step="0.01"
                className="rounded border border-black/15 px-3 py-2 dark:border-white/15"
                value={tariffRate ?? ""}
                onChange={(e) =>
                  setTariffRate(e.target.value === "" ? undefined : Number(e.target.value))
                }
              />
            </label>
          </div>
        </fieldset>

        <fieldset className="flex flex-col gap-4">
          <legend className="mb-1 font-medium">Техника</legend>
          {appliances.map((appliance, index) => (
            <div key={index} className="flex items-end gap-3">
              <label className="flex flex-1 flex-col gap-1 text-sm">
                Название
                <input
                  className="rounded border border-black/15 px-3 py-2 dark:border-white/15"
                  value={appliance.name}
                  onChange={(e) => updateAppliance(index, { name: e.target.value })}
                  placeholder="Напр. Холодильник"
                />
              </label>
              <label className="flex w-32 flex-col gap-1 text-sm">
                Мощность, Вт
                <input
                  type="number"
                  min={0}
                  className="rounded border border-black/15 px-3 py-2 dark:border-white/15"
                  value={appliance.power_watts ?? ""}
                  onChange={(e) =>
                    updateAppliance(index, {
                      power_watts: e.target.value === "" ? undefined : Number(e.target.value),
                    })
                  }
                />
              </label>
              <label className="flex w-20 flex-col gap-1 text-sm">
                Кол-во
                <input
                  type="number"
                  min={1}
                  className="rounded border border-black/15 px-3 py-2 dark:border-white/15"
                  value={appliance.quantity}
                  onChange={(e) => updateAppliance(index, { quantity: Number(e.target.value) })}
                />
              </label>
              <button
                type="button"
                onClick={() => removeAppliance(index)}
                className="h-10 px-3 text-sm text-foreground/60 hover:text-foreground"
              >
                Удалить
              </button>
            </div>
          ))}
          <button
            type="button"
            onClick={addAppliance}
            className="self-start text-sm font-medium text-foreground/80 hover:text-foreground"
          >
            + Добавить прибор
          </button>
        </fieldset>

        <div className="flex items-center gap-4">
          <button
            type="submit"
            disabled={status === "submitting"}
            className="rounded-full bg-foreground px-6 py-2.5 text-sm font-medium text-background transition-colors hover:bg-foreground/85 disabled:opacity-50"
          >
            {status === "submitting" ? "Сохраняем..." : "Сохранить и продолжить"}
          </button>
          {status === "error" && (
            <span className="text-sm text-red-600">
              Не удалось сохранить анкету. Проверьте, что backend запущен.
            </span>
          )}
        </div>
      </form>
    </div>
  );
}
