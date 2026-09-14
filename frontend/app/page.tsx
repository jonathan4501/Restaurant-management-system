import Link from "next/link";

const stations = [
  { href: "/login", label: "Login", note: "device enrolment + PIN pad (WS07)" },
  { href: "/order", label: "Order", note: "waiter / guest / qr modes (WS07)" },
  { href: "/kds", label: "Kitchen", note: "three columns, timers (WS08)" },
  { href: "/cashier", label: "Cashier", note: "bills, payments, shift (WS09)" },
  { href: "/owner", label: "Owner", note: "variance first (WS10)" },
];

export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center gap-3 px-4 py-8">
      <h1 className="text-2xl font-semibold">RENZY</h1>
      <p className="text-sm opacity-70">Foundation shell. Each station is a workstream; see docs/tasks/.</p>
      {stations.map((s) => (
        <Link
          key={s.href}
          href={s.href}
          className="flex min-h-14 items-center justify-between rounded-lg border px-4 py-3 text-lg"
        >
          <span>{s.label}</span>
          <span className="text-xs opacity-60">{s.note}</span>
        </Link>
      ))}
    </main>
  );
}
