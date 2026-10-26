/** Formatação dos números do teste de carga; null/ausente vira "—". */

const MISSING = "—";

export function fmtMs(value: number | null | undefined): string {
  if (typeof value !== "number") return MISSING;
  return value >= 1000 ? `${(value / 1000).toFixed(2)} s` : `${value.toFixed(0)} ms`;
}

export function fmtRate(value: number | null | undefined): string {
  return typeof value === "number" ? `${value.toFixed(1)}/s` : MISSING;
}

/** ``ratio`` é uma fração de 0 a 1. */
export function fmtPercent(ratio: number | null | undefined): string {
  return typeof ratio === "number" ? `${(ratio * 100).toFixed(1)}%` : MISSING;
}

export function fmtSeconds(value: number | null | undefined): string {
  return typeof value === "number" ? `${value.toFixed(1)} s` : MISSING;
}

export function fmtMb(value: number | null | undefined): string {
  return typeof value === "number" ? `${value.toFixed(0)} MB` : MISSING;
}

/** Megabytes de tamanho pequeno (cópias de fixtures): uma casa decimal abaixo de 100 MB. */
export function fmtMbFine(value: number | null | undefined): string {
  if (typeof value !== "number") return MISSING;
  return value < 100 ? `${value.toFixed(1)} MB` : fmtMb(value);
}

/** "20261024_100000_abc1234" -> "24/10/2026 10:00:00" (o id começa pelo horário local). */
export function fmtLoadId(loadId: string): string {
  const match = /^(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})/.exec(loadId);
  if (!match) return loadId;
  const [, y, mo, d, h, mi, s] = match;
  return `${d}/${mo}/${y} ${h}:${mi}:${s}`;
}

export function fmtCpm(value: number | null | undefined): string {
  return typeof value === "number" ? `${value.toFixed(1)} casos/min` : MISSING;
}

/** Média com uma casa decimal (ex.: tool-calls por caso). */
export function fmtMean(value: number | null | undefined): string {
  return typeof value === "number" ? value.toFixed(1) : MISSING;
}
