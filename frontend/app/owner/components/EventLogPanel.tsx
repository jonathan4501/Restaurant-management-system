"use client";

import { useInfiniteQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { fetchEventLog, problemMessage } from "../lib/api";
import { mergeEventPages, replaceEventPage } from "../lib/cursor";
import { formatClock } from "../lib/dates";
import type { EventLogRow, LogFilter, LogPreset } from "../lib/types";

interface Props {
  initialPreset?: LogPreset | null;
}

function presetToFilter(preset: LogPreset | null | undefined): LogFilter {
  if (!preset) return {};
  switch (preset.kind) {
    case "voids":
      return { type: "ORDER_VOIDED", flagged: true };
    case "discounts":
      return {
        type: "ORDER_DISCOUNTED",
        actor_id: preset.actor_id,
      };
    case "reopens":
      return { type: "SESSION_REOPENED" };
    case "cash":
      return { type: "SHIFT_CLOSED" };
    case "gaps":
      return { flagged: true };
    default:
      return {};
  }
}

function describe(row: EventLogRow): string {
  const bits = [row.type.replaceAll("_", " ")];
  if (row.reason_code) bits.push(row.reason_code);
  if (row.authorised_by) bits.push(`auth ${row.authorised_by}`);
  return bits.join(" · ");
}

export function EventLogPanel({ initialPreset = null }: Props) {
  const [filter, setFilter] = useState<LogFilter>(() => presetToFilter(initialPreset));
  const [typeInput, setTypeInput] = useState(filter.type ?? "");
  const [actorId, setActorId] = useState(filter.actor_id ?? "");
  const [expanded, setExpanded] = useState<number | null>(null);

  useEffect(() => {
    setFilter(presetToFilter(initialPreset));
    setTypeInput(presetToFilter(initialPreset).type ?? "");
    setActorId(presetToFilter(initialPreset).actor_id ?? "");
  }, [initialPreset]);

  const query = useInfiniteQuery({
    queryKey: ["owner-events", filter],
    queryFn: ({ pageParam }) => fetchEventLog(filter, pageParam as number | null | undefined),
    initialPageParam: null as number | null,
    getNextPageParam: (last) => (last.has_more ? last.next_cursor : undefined),
  });

  const rows = useMemo(() => {
    const pages = query.data?.pages ?? [];
    let merged: EventLogRow[] = [];
    for (let i = 0; i < pages.length; i += 1) {
      const page = pages[i]!.events;
      merged = i === 0 ? replaceEventPage(page) : mergeEventPages(merged, page);
    }
    return merged;
  }, [query.data]);

  const staffOptions = useMemo(() => {
    const map = new Map<string, string>();
    for (const row of rows) {
      if (row.actor_id && row.actor) map.set(row.actor_id, row.actor);
    }
    return [...map.entries()].sort((a, b) => a[1].localeCompare(b[1]));
  }, [rows]);

  function applyFilters() {
    setFilter({
      type: typeInput.trim() || undefined,
      actor_id: actorId || undefined,
      flagged: filter.flagged,
    });
  }

  return (
    <section data-testid="event-log">
      <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Every action, in order</h2>
          <p className="text-xs text-[var(--ink-3)]">
            Append-only. Nothing here can be edited or deleted.
          </p>
        </div>
      </div>

      <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-end">
        <label className="text-xs uppercase tracking-wide text-[var(--ink-3)]">
          Staff
          <select
            data-testid="log-filter-staff"
            value={actorId}
            onChange={(e) => setActorId(e.target.value)}
            className="mt-1 block min-h-14 w-full min-w-[10rem] rounded-lg border border-[var(--line)] bg-[var(--surface-2)] px-3 text-sm text-[var(--ink)] sm:w-auto"
          >
            <option value="">All staff</option>
            {staffOptions.map(([id, name]) => (
              <option key={id} value={id}>
                {name}
              </option>
            ))}
          </select>
        </label>
        <label className="text-xs uppercase tracking-wide text-[var(--ink-3)]">
          Event type
          <input
            data-testid="log-filter-type"
            value={typeInput}
            onChange={(e) => setTypeInput(e.target.value)}
            placeholder="ORDER_VOIDED"
            className="mt-1 block min-h-14 w-full min-w-[12rem] rounded-lg border border-[var(--line)] bg-[var(--surface-2)] px-3 text-sm sm:w-auto"
          />
        </label>
        <label className="flex min-h-14 items-center gap-2 text-sm">
          <input
            data-testid="log-filter-flagged"
            type="checkbox"
            checked={Boolean(filter.flagged)}
            onChange={(e) => setFilter((f) => ({ ...f, flagged: e.target.checked || undefined }))}
          />
          Flagged only
        </label>
        <button
          type="button"
          data-testid="log-filter-apply"
          onClick={applyFilters}
          className="flex min-h-14 items-center rounded-lg bg-[var(--accent)] px-4 text-sm font-semibold text-[var(--accent-ink)]"
        >
          Apply
        </button>
      </div>

      {query.isError ? (
        <p role="alert" className="mb-3 text-sm text-[var(--danger)]">
          {problemMessage(query.error, "Could not load the event log")}
        </p>
      ) : null}

      <ul className="divide-y divide-[var(--line)] border border-[var(--line)]">
        {rows.map((row) => {
          const open = expanded === row.seq;
          return (
            <li
              key={row.seq}
              data-testid={`log-row-${row.seq}`}
              data-flagged={row.flagged ? "true" : "false"}
              className={row.flagged ? "bg-[color-mix(in_srgb,var(--danger)_14%,transparent)]" : ""}
            >
              <button
                type="button"
                className="grid w-full grid-cols-[4rem_minmax(0,1fr)] gap-x-3 gap-y-1 px-3 py-3 text-left sm:grid-cols-[4rem_6rem_minmax(0,1fr)]"
                onClick={() => setExpanded(open ? null : row.seq)}
              >
                <span className="num text-[11px] text-[var(--ink-3)]">{formatClock(row.created_at)}</span>
                <span className="text-[10px] font-bold uppercase tracking-wide text-[var(--ink-3)]">
                  {row.actor_role}
                  {row.actor ? ` · ${row.actor}` : ""}
                </span>
                <span className="col-span-2 text-sm text-[var(--ink-2)] sm:col-span-1">
                  <strong className={row.flagged ? "text-[var(--danger)]" : "text-[var(--ink)]"}>
                    {row.type}
                  </strong>
                  {" — "}
                  {describe(row)}
                </span>
              </button>
              {open ? (
                <pre
                  data-testid={`log-payload-${row.seq}`}
                  className="overflow-x-auto border-t border-[var(--line)] bg-[var(--surface-2)] px-3 py-2 text-xs text-[var(--ink-2)]"
                >
                  {JSON.stringify(row.payload, null, 2)}
                </pre>
              ) : null}
            </li>
          );
        })}
      </ul>

      {query.hasNextPage ? (
        <button
          type="button"
          data-testid="log-load-more"
          disabled={query.isFetchingNextPage}
          onClick={() => void query.fetchNextPage()}
          className="mt-4 flex min-h-14 w-full items-center justify-center rounded-lg border border-[var(--line)] bg-[var(--surface)] text-sm"
        >
          {query.isFetchingNextPage ? "Loading…" : "Load older events"}
        </button>
      ) : null}
    </section>
  );
}
