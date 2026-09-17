"use client";

import Link from "next/link";

import { ConnectivityBadge } from "@/components/ConnectivityBadge";

interface Props {
  name: string;
  title: string;
  onLogout: () => void;
  children: React.ReactNode;
}

export function OwnerShell({ name, title, onLogout, children }: Props) {
  return (
    <main className="staff-shell staff-theme min-h-screen px-4 py-4 sm:px-6">
      <header className="mb-5 flex flex-wrap items-center justify-between gap-3 border-b border-[var(--line)] pb-4">
        <div>
          <p className="text-xs uppercase tracking-wide text-[var(--ink-3)]">RENZY · Owner</p>
          <h1 className="text-xl font-semibold sm:text-2xl">{title}</h1>
          <p className="text-sm text-[var(--ink-3)]">{name}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <ConnectivityBadge />
          <Link
            href="/owner"
            data-testid="owner-nav-dashboard"
            className="flex min-h-14 items-center rounded-lg border border-[var(--line)] bg-[var(--surface)] px-4 text-sm"
          >
            Dashboard
          </Link>
          <Link
            href="/owner/events"
            data-testid="owner-nav-events"
            className="flex min-h-14 items-center rounded-lg border border-[var(--line)] bg-[var(--surface)] px-4 text-sm"
          >
            Event log
          </Link>
          <a
            href="/admin/"
            data-testid="owner-admin-menu"
            className="flex min-h-14 items-center rounded-lg border border-[var(--line)] bg-[var(--surface)] px-4 text-sm"
          >
            Menu admin
          </a>
          <a
            href="/admin/accounts/staff/"
            data-testid="owner-admin-staff"
            className="flex min-h-14 items-center rounded-lg border border-[var(--line)] bg-[var(--surface)] px-4 text-sm"
          >
            Staff admin
          </a>
          <button
            type="button"
            data-testid="owner-logout"
            onClick={onLogout}
            className="flex min-h-14 items-center rounded-lg border border-[var(--line)] px-4 text-sm text-[var(--ink-2)]"
          >
            Sign out
          </button>
        </div>
      </header>
      {children}
    </main>
  );
}
