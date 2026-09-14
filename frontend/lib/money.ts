/**
 * Money is an integer number of pesewas everywhere in the app. These two functions are the ONLY
 * place pesewas become a string or a string becomes pesewas. No floats, no `/ 100` elsewhere.
 */

export type Pesewas = number;

/** 7500 → "GH₵ 75.00"; 1234567 → "GH₵ 12,345.67"; -2000 → "-GH₵ 20.00" */
export function formatPesewas(value: Pesewas, opts: { symbol?: boolean } = {}): string {
  if (!Number.isInteger(value)) {
    throw new TypeError(`formatPesewas expects an integer number of pesewas, got ${value}`);
  }
  const sign = value < 0 ? "-" : "";
  const abs = Math.abs(value);
  const cedis = Math.floor(abs / 100);
  const pesewas = abs % 100;
  const grouped = cedis.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  const body = `${grouped}.${pesewas.toString().padStart(2, "0")}`;
  return opts.symbol === false ? `${sign}${body}` : `${sign}GH₵ ${body}`;
}

/**
 * Parse what a cashier types ("30", "30.5", "1,250.00", "GH₵ 12") into pesewas without ever
 * touching a float. Returns null for anything that is not a non-negative amount.
 */
export function parsePesewasInput(raw: string): Pesewas | null {
  const cleaned = raw.replace(/GH₵|GHS|,|\s/g, "");
  if (!/^\d*(\.\d{0,2})?$/.test(cleaned) || cleaned === "" || cleaned === ".") return null;
  const [whole = "0", frac = ""] = cleaned.split(".");
  const cedis = parseInt(whole || "0", 10);
  const pesewas = parseInt((frac + "00").slice(0, 2), 10);
  return cedis * 100 + pesewas;
}
