"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/onboarding", label: "Анкета" },
  { href: "/bills", label: "Загрузка счёта" },
  { href: "/dashboard", label: "Дашборд" },
  { href: "/chat", label: "Энергокоуч" },
];

export default function NavBar() {
  const pathname = usePathname();

  return (
    <header className="border-b border-black/10 dark:border-white/10">
      <nav className="mx-auto flex max-w-4xl items-center gap-6 px-4 py-4">
        <Link href="/" className="font-semibold">
          EnergyPilot AI
        </Link>
        <div className="flex gap-4 text-sm">
          {LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className={
                pathname === link.href
                  ? "font-medium text-foreground"
                  : "text-foreground/60 hover:text-foreground"
              }
            >
              {link.label}
            </Link>
          ))}
        </div>
      </nav>
    </header>
  );
}
