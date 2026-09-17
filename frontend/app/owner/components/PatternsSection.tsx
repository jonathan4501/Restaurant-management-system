"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { formatPesewas } from "@/lib/money";

import { hourlyBars, paymentMixRows } from "../lib/aggregations";
import { formatSeconds, MONEY_TAKEN } from "../lib/labels";
import type { Patterns } from "../lib/types";

interface Props {
  patterns: Patterns;
  currentHour: number | null;
}

export function PatternsSection({ patterns, currentHour }: Props) {
  const bars = hourlyBars(patterns.money_taken_by_hour, { currentHour });
  const mix = paymentMixRows(patterns.payment_method_mix);
  const sellers = patterns.best_sellers_by_value.slice(0, 8);
  const stations = patterns.station_timing;

  return (
    <section data-testid="patterns" className="mb-8 space-y-6">
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <div className="border border-[var(--line)] bg-[var(--surface)] p-3">
          <h2 className="mb-3 text-lg font-semibold">{MONEY_TAKEN} by hour</h2>
          {bars.length === 0 ? (
            <p className="text-sm text-[var(--ink-3)]">No settled bills in this window yet.</p>
          ) : (
            <div className="h-64 w-full" data-testid="hourly-chart">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={bars} margin={{ top: 20, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid stroke="var(--line)" vertical={false} strokeDasharray="3 3" />
                  <XAxis
                    dataKey="label"
                    tick={{ fill: "var(--ink-3)", fontSize: 11 }}
                    axisLine={{ stroke: "var(--line)" }}
                    tickLine={false}
                  />
                  <YAxis
                    tick={{ fill: "var(--ink-3)", fontSize: 11 }}
                    axisLine={false}
                    tickLine={false}
                    tickFormatter={(v: number) => `${Math.round(v / 100)}`}
                    width={40}
                  />
                  <Tooltip
                    cursor={{ fill: "var(--surface-3)" }}
                    contentStyle={{
                      background: "var(--surface-2)",
                      border: "1px solid var(--line)",
                      color: "var(--ink)",
                    }}
                    formatter={(value: number | string) => [
                      formatPesewas(Number(value)),
                      MONEY_TAKEN,
                    ]}
                    isAnimationActive={false}
                  />
                  <Bar
                    dataKey="money_taken_pesewas"
                    radius={[4, 4, 0, 0]}
                    isAnimationActive={false}
                  >
                    {bars.map((row) => (
                      <Cell
                        key={row.hour}
                        fill="var(--accent)"
                        fillOpacity={row.inProgress ? 0.42 : 1}
                      />
                    ))}
                    <LabelList
                      dataKey="money_taken_pesewas"
                      position="top"
                      fill="var(--ink-2)"
                      fontSize={11}
                      formatter={(value: number | string) => {
                        const n = Number(value);
                        const peak = bars.find((b) => b.isPeak);
                        if (!peak || peak.money_taken_pesewas !== n) return "";
                        return formatPesewas(n);
                      }}
                    />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
              {bars.some((b) => b.inProgress) ? (
                <p className="mt-1 text-xs text-[var(--ink-3)]">Dim bar: hour still in progress.</p>
              ) : null}
            </div>
          )}
        </div>

        <div className="border border-[var(--line)] bg-[var(--surface)] p-3">
          <h2 className="mb-3 text-lg font-semibold">How people paid</h2>
          <ul className="space-y-3" data-testid="payment-mix">
            {mix.length === 0 ? (
              <li className="text-sm text-[var(--ink-3)]">No payments yet.</li>
            ) : (
              mix.map((row) => (
                <li key={row.method}>
                  <div className="mb-1 flex justify-between text-sm">
                    <span>{row.label}</span>
                    <span className="num">{formatPesewas(row.pesewas)}</span>
                  </div>
                  <div className="h-[7px] w-full bg-[var(--surface-3)]">
                    <div
                      className="h-full bg-[var(--accent)]"
                      style={{ width: `${Math.round(row.share * 100)}%` }}
                    />
                  </div>
                </li>
              ))
            )}
          </ul>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="border border-[var(--line)] bg-[var(--surface)] p-3">
          <h2 className="mb-3 text-lg font-semibold">Best sellers</h2>
          <ul className="space-y-3" data-testid="best-sellers">
            {sellers.length === 0 ? (
              <li className="text-sm text-[var(--ink-3)]">No lines settled yet.</li>
            ) : (
              sellers.map((row) => {
                const max = sellers[0]?.value_pesewas || 1;
                const share = row.value_pesewas / max;
                return (
                  <li key={row.name}>
                    <div className="mb-1 flex justify-between gap-3 text-sm">
                      <span>
                        {row.name}{" "}
                        <span className="text-[var(--ink-3)]">{row.quantity} sold</span>
                      </span>
                      <span className="num shrink-0">{formatPesewas(row.value_pesewas)}</span>
                    </div>
                    <div className="h-[7px] w-full bg-[var(--surface-3)]">
                      <div
                        className="h-full bg-[var(--accent)]"
                        style={{ width: `${Math.round(share * 100)}%` }}
                      />
                    </div>
                  </li>
                );
              })
            )}
          </ul>
        </div>

        <div className="border border-[var(--line)] bg-[var(--surface)] p-3">
          <h2 className="mb-3 text-lg font-semibold">Order to ready</h2>
          <table className="w-full text-left text-sm" data-testid="station-timing">
            <thead className="text-xs uppercase text-[var(--ink-3)]">
              <tr>
                <th className="py-2 font-medium">Station</th>
                <th className="py-2 font-medium">Average</th>
                <th className="py-2 font-medium">Lines</th>
              </tr>
            </thead>
            <tbody>
              {stations.length === 0 ? (
                <tr>
                  <td colSpan={3} className="py-3 text-[var(--ink-3)]">
                    No timing yet.
                  </td>
                </tr>
              ) : (
                stations.map((s) => (
                  <tr key={s.station} className="border-t border-[var(--line)]">
                    <td className="py-3">{s.station}</td>
                    <td className="num py-3">{formatSeconds(s.average_seconds)}</td>
                    <td className="num py-3">{s.lines}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
