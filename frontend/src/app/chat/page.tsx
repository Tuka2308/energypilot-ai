"use client";

import { useState } from "react";
import Link from "next/link";
import { sendChatMessage } from "@/lib/api";
import { getProfileId } from "@/lib/profile";

interface ChatEntry {
  role: "user" | "coach";
  text: string;
}

export default function ChatPage() {
  const [profileId] = useState(() => getProfileId());
  const [message, setMessage] = useState("");
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
