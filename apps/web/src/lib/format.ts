/** Presentation helpers. Locale-aware, and defensive about bad input. */

const CURRENCY = new Intl.NumberFormat("en-CA", {
  style: "currency",
  currency: "CAD",
  maximumFractionDigits: 0,
});

const TIME = new Intl.DateTimeFormat("en-CA", { hour: "numeric", minute: "2-digit" });
const DAY = new Intl.DateTimeFormat("en-CA", { weekday: "short", month: "short", day: "numeric" });

export function money(value: number): string {
  return CURRENCY.format(value);
}

export function budget(min: number, max: number): string {
  return `${compactMoney(min)} – ${compactMoney(max)}`;
}

function compactMoney(value: number): string {
  if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `$${Math.round(value / 1000)}k`;
  return money(value);
}

export function time(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "—" : TIME.format(date);
}

export function day(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "—" : DAY.format(date);
}

/** "in 2h", "3d ago" — compact and human. */
export function relative(iso: string, now: Date = new Date()): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";

  const seconds = Math.round((date.getTime() - now.getTime()) / 1000);
  const abs = Math.abs(seconds);
  const suffix = seconds < 0 ? " ago" : "";
  const prefix = seconds > 0 ? "in " : "";

  if (abs < 60) return "just now";
  if (abs < 3600) return `${prefix}${Math.round(abs / 60)}m${suffix}`;
  if (abs < 86_400) return `${prefix}${Math.round(abs / 3600)}h${suffix}`;
  return `${prefix}${Math.round(abs / 86_400)}d${suffix}`;
}

export function isOverdue(iso: string, now: Date = new Date()): boolean {
  const date = new Date(iso);
  return !Number.isNaN(date.getTime()) && date.getTime() < now.getTime();
}

export function initials(name: string): string {
  return name
    .split(/[\s&]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

export function titleCase(value: string): string {
  return value.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Render tool arguments as short, readable label/value pairs. */
export function argEntries(args: Record<string, unknown>): [string, string][] {
  return Object.entries(args).map(([key, value]) => [
    titleCase(key),
    typeof value === "string" ? value : JSON.stringify(value),
  ]);
}
