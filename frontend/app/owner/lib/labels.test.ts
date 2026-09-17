import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { MONEY_TAKEN, TOTAL_COLLECTED } from "./labels";

const here = path.dirname(fileURLToPath(import.meta.url));
const ownerRoot = path.resolve(here, "..");

/** Built at runtime so the literals never appear in the scanned UI sources. */
const forbidden = ["Rev" + "enue", "Pro" + "fit"] as const;

function walkTsx(dir: string): string[] {
  const out: string[] = [];
  for (const name of readdirSync(dir)) {
    const full = path.join(dir, name);
    if (statSync(full).isDirectory()) out.push(...walkTsx(full));
    else if (name.endsWith(".tsx") && !name.includes(".test.")) out.push(full);
  }
  return out;
}

describe("owner money labels", () => {
  it("exports the binding gross labels", () => {
    expect(MONEY_TAKEN).toBe("Money taken");
    expect(TOTAL_COLLECTED).toBe("Total collected");
  });

  it("never puts the wrong gross words in owner UI sources", () => {
    const files = walkTsx(ownerRoot);
    expect(files.length).toBeGreaterThan(0);
    const hits: string[] = [];
    for (const file of files) {
      const text = readFileSync(file, "utf8");
      for (const word of forbidden) {
        if (text.includes(word)) hits.push(`${path.relative(ownerRoot, file)}: ${word}`);
      }
    }
    expect(hits).toEqual([]);
  });
});
