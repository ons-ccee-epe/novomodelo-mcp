import type { LoadConfigRecord, LoadRun, LoadStats } from "@/shared/types";

/** Métrica comparável entre duas cargas; ``lowerIsBetter`` define o que é melhora. */
export interface MetricSpec {
  key: "throughput_cps" | "error_rate" | "p50_ms" | "p95_ms" | "p99_ms";
  label: string;
  lowerIsBetter: boolean;
}

export const COMPARED_METRICS: MetricSpec[] = [
  { key: "throughput_cps", label: "Vazão", lowerIsBetter: false },
  { key: "error_rate", label: "Taxa de erro", lowerIsBetter: true },
  { key: "p50_ms", label: "Latência p50", lowerIsBetter: true },
  { key: "p95_ms", label: "Latência p95", lowerIsBetter: true },
  { key: "p99_ms", label: "Latência p99", lowerIsBetter: true },
];

export type Trend = "better" | "worse" | "flat";

export interface MetricDelta {
  spec: MetricSpec;
  current: number | null;
  previous: number | null;
  /** current - previous; null se algum dos lados não mediu. */
  delta: number | null;
  /** Variação relativa ao anterior (fração); null se o anterior é 0 ou ausente. */
  relative: number | null;
  trend: Trend;
}

export function trendOf(delta: number | null, lowerIsBetter: boolean): Trend {
  if (delta === null || delta === 0) return "flat";
  const improved = lowerIsBetter ? delta < 0 : delta > 0;
  return improved ? "better" : "worse";
}

export function compareStats(current: LoadStats, previous: LoadStats): MetricDelta[] {
  return COMPARED_METRICS.map((spec) => {
    const now = current[spec.key];
    const before = previous[spec.key];
    const delta = now === null || before === null ? null : now - before;
    return {
      spec,
      current: now,
      previous: before,
      delta,
      relative: delta !== null && before ? delta / before : null,
      trend: trendOf(delta, spec.lowerIsBetter),
    };
  });
}

export interface ToolDelta {
  tool: string;
  current: number | null;
  previous: number | null;
  delta: number | null;
  trend: Trend;
}

/** p95 por tool nas duas cargas (só as tools presentes nas duas). */
export function compareToolP95(current: LoadRun, previous: LoadRun): ToolDelta[] {
  return Object.keys(current.per_tool)
    .filter((tool) => tool in previous.per_tool)
    .sort()
    .map((tool) => {
      const now = current.per_tool[tool].p95_ms;
      const before = previous.per_tool[tool].p95_ms;
      const delta = now === null || before === null ? null : now - before;
      return { tool, current: now, previous: before, delta, trend: trendOf(delta, true) };
    });
}

const CONFIG_LABELS: Array<[keyof LoadConfigRecord, string]> = [
  ["concurrency", "concorrência"],
  ["duration_seconds", "duração"],
  ["iterations", "iterações"],
  ["tools", "tools"],
  ["timeout_seconds", "timeout"],
];

/** Parâmetros que diferem entre as duas cargas; vazio = comparação direta. */
export function configDifferences(a: LoadConfigRecord, b: LoadConfigRecord): string[] {
  return CONFIG_LABELS.filter(
    ([key]) => JSON.stringify(a[key] ?? null) !== JSON.stringify(b[key] ?? null),
  ).map(([, label]) => label);
}
