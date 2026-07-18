"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { sendChatMessage } from "@/lib/api";
import { useProfileId } from "@/lib/profile";

interface ChatEntry {
  role: "user" | "coach";
  text: string;
}

// useSearchParams требует Suspense-границу в App Router — поэтому страница
// разбита на обёртку и внутренний компонент.
export default function ChatPage() {
  return (
    <Suspense fallback={<p className="text-sm text-foreground/60">Загрузка…</p>}>
      <ChatPageInner />
    </Suspense>
  );
}

function ChatPageInner() {
  const searchParams = useSearchParams();
  // useProfileId вместо useState(getProfileId): без hydration mismatch
  // (см. lib/profile.ts).
  const profileId = useProfileId();
  // Дашборд передаёт готовый вопрос через ?q= — поле уже заполнено, остаётся
  // нажать «Отправить». Один переход вместо «перейди и перепечатай вопрос».
  const [message, setMessage] = useState(() => searchParams.get("q") ?? "");
  const [history, setHistory] = useState<ChatEntry[]>([]);
  const [status, setStatus] = useState<"idle" | "sending">("idle");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!message.trim() || !profileId) return;

    const userMessage = message;
    setHistory((prev) => [...prev, { role: "user", text: userMessage }]);
    setMessage("");
    setStatus("sending");

    try {
      const response = await sendChatMessage({
        profile_id: profileId,
        message: userMessage,
      });
      setHistory((prev) => [...prev, { role: "coach", text: response.reply }]);
    } finally {
      setStatus("idle");
    }
  }

  if (profileId === undefined) {
    // Гидрация ещё идёт — тот же плейсхолдер, что и серверный Suspense-fallback.
    return <p className="text-sm text-foreground/60">Загрузка…</p>;
  }

  if (!profileId) {
    return (
      <div className="flex flex-col gap-3">
        <h1 className="text-2xl font-semibold">Энергокоуч</h1>
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

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold">Энергокоуч</h1>
        <p className="text-sm text-foreground/60">
          Советы по экономии на основе вашего профиля, прогноза и тарифа.
        </p>
      </div>

      <div className="flex min-h-[240px] flex-col gap-3 rounded-lg border border-black/10 p-4 dark:border-white/10">
        {history.length === 0 && (
          <p className="text-sm text-foreground/50">
            Спросите, например: «Как снизить счёт за отопление?»
          </p>
        )}
        {history.map((entry, i) => (
          <div
            key={i}
            className={
              entry.role === "user"
                ? "self-end rounded-lg bg-foreground px-3 py-2 text-sm text-background"
                : "self-start rounded-lg bg-black/5 px-3 py-2 text-sm dark:bg-white/10"
            }
          >
            {entry.text}
          </div>
        ))}
        {status === "sending" && (
          <p className="self-start text-sm text-foreground/50">
            Коуч печатает…
          </p>
        )}
      </div>

      <form onSubmit={handleSubmit} className="flex gap-3">
        <input
          className="flex-1 rounded border border-black/15 px-3 py-2 text-sm dark:border-white/15"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="Ваш вопрос энергокоучу"
        />
        <button
          type="submit"
          disabled={status === "sending"}
          className="rounded-full bg-foreground px-6 py-2.5 text-sm font-medium text-background transition-colors hover:bg-foreground/85 disabled:opacity-50"
        >
          Отправить
        </button>
      </form>
    </div>
  );
}
