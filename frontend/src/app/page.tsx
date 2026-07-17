import Link from "next/link";

const STEPS = [
  {
    href: "/onboarding",
    title: "1. Заполните анкету",
    description: "Квартира, техника и тариф — одной формой.",
  },
  {
    href: "/bills",
    title: "2. Загрузите счёт",
    description: "Фото или PDF квитанции, с возможностью ручной правки.",
  },
  {
    href: "/dashboard",
    title: "3. Смотрите прогноз",
    description: "Прогноз следующего счёта, разбивка по категориям, аномалии.",
  },
  {
    href: "/chat",
    title: "4. Спросите энергокоуча",
    description: "Персональные советы по экономии на основе ваших данных.",
  },
];

export default function Home() {
  return (
    <div className="flex flex-col gap-10">
      <div className="flex flex-col gap-3">
        <h1 className="text-3xl font-semibold tracking-tight">
          EnergyPilot AI
        </h1>
        <p className="max-w-xl text-foreground/70">
          Прогноз счёта за электричество, разбор структуры расхода и
          персональные рекомендации по экономии — до того, как придёт
          квитанция.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        {STEPS.map((step) => (
          <Link
            key={step.href}
            href={step.href}
            className="flex flex-col gap-2 rounded-lg border border-black/10 p-5 transition-colors hover:border-black/30 dark:border-white/10 dark:hover:border-white/30"
          >
            <span className="font-medium">{step.title}</span>
            <span className="text-sm text-foreground/60">
              {step.description}
            </span>
          </Link>
        ))}
      </div>
    </div>
  );
}
