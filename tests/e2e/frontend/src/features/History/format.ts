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
