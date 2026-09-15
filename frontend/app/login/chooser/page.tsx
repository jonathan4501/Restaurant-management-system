"use client";

import Link from "next/link";

const STATIONS = [
  { href: "/order", label: "Order", note: "Tables and menu" },
  { href: "/kds", label: "Kitchen", note: "Ticket display" },
  { href: "/cashier", label: "Cashier", note: "Payments and shift" },
  { href: "/owner", label: "Owner", note: "Reports" },
];

export default function ManagerChooserPage() {
  return (
    <main className="staff-shell staff-theme mx-auto flex min-h-screen max-w-md flex-col justify-center gap-3 px-4 py-8">
      <h1 className="text-2xl font-semibold">Choose station</h1>
      {STATIONS.map((s) => (
        <Link key={s.href} href={s.href} data-testid={`chooser-${s.href.slice(1)}`} className="flex min-h-16 items-center justify-between rounded-xl border border-[var(--line)] bg-[var(--surface)] px-4 py-3 text-lg active:bg-[var(--surface-3)]">
          <span>{s.label}</span><span className="text-xs text-[var(--ink-3)]">{s.note}</span>
        </Link>
      ))}
    </main>
  );
}
