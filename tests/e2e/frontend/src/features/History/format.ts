const pad = (n: number) => String(n).padStart(2, "0");

export function formatDate(timestamp: string): string {
  const d = new Date(timestamp);
  if (Number.isNaN(d.getTime())) return timestamp;
  return `${pad(d.getDate())}/${pad(d.getMonth() + 1)} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export const decimal = (n: number) => n.toFixed(1).replace(".", ",");

export function formatDelta(delta: number | null): {
  text: string;
  trend: "up" | "down" | "none";
} {
  if (delta === null) return { text: "—", trend: "none" };
  const rounded = Math.round(delta * 10) / 10;
  if (rounded === 0) return { text: "0,0 pp", trend: "none" };
  if (rounded > 0) return { text: `▲ +${decimal(rounded)} pp`, trend: "up" };
  return { text: `▼ −${decimal(-rounded)} pp`, trend: "down" };
}

export type RateBand = "good" | "mid" | "bad" | "none";

/** Faixa da taxa de aprovação (0–100) que dá a cor da %. */
export function rateBand(rate: number | null): RateBand {
  if (rate === null) return "none";
  if (rate >= 80) return "good";
  if (rate >= 50) return "mid";
  return "bad";
}

/** "45s", "12m30s" ou "1h02m". */
export function formatDuration(ms: number): string {
  const total = Math.round(ms / 1000);
  if (total < 60) return `${total}s`;
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  if (h > 0) return `${h}h${pad(m)}m`;
  return `${m}m${pad(total % 60)}s`;
}
