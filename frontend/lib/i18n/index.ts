"use client";
import { create } from "zustand";
import { en, type GuestStringKey } from "./en";
import { tw } from "./tw";
export type Locale = "en" | "tw";
function format(template: string, vars?: Record<string, string>): string {
  if (!vars) return template;
  return Object.entries(vars).reduce((s, [k, v]) => s.replace(`{${k}}`, v), template);
}
export const useI18n = create<{ locale: Locale; setLocale: (l: Locale) => void; t: (key: GuestStringKey, vars?: Record<string, string>) => string }>((set, get) => ({
  locale: "en",
  setLocale: (locale) => set({ locale }),
  t: (key, vars) => format((get().locale === "tw" ? { ...en, ...tw } : en)[key], vars),
}));
