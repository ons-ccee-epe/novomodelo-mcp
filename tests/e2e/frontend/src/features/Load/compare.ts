import type {
  AgentConfigRecord,
  AgentLoadRun,
  LoadConfigRecord,
  LoadRun,
  LoadStats,
} from "@/shared/types";

/** Métrica comparável entre duas cargas; ``lowerIsBetter`` define o que é melhora. */
export interface MetricSpec {
  key: "throughput_cps" | "throughput_cpm" | "pass_rate" | "error_rate" | "p50_ms" | "p95_ms" | "p99_ms";
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

export const AGENT_COMPARED_METRICS: MetricSpec[] = [
  { key: "throughput_cpm", label: "Vazão (casos/min)", lowerIsBetter: false },
  { key: "pass_rate", label: "Aprovação", lowerIsBetter: false },
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

function metricOf(stats: LoadStats, key: MetricSpec["key"]): number | null {
  const value = (stats as unknown as Record<string, number | null | undefined>)[key];
  return typeof value === "number" ? value : null;
}

export function compareStats(
  current: LoadStats,
  previous: LoadStats,
  specs: MetricSpec[] = COMPARED_METRICS,
): MetricDelta[] {
  return specs.map((spec) => {
    const now = metricOf(current, spec.key);
    const before = metricOf(previous, spec.key);
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

/** p95 de uma tool (modo tools) ou de um caso (modo agente; ``tool`` guarda o id do caso). */
export interface ToolDelta {
  tool: string;
  current: number | null;
  previous: number | null;
  delta: number | null;
  trend: Trend;
}

function compareP95(
  current: Record<string, LoadStats>,
  previous: Record<string, LoadStats>,
): ToolDelta[] {
  return Object.keys(current)
    .filter((key) => key in previous)
    .sort()
    .map((key) => {
      const now = current[key].p95_ms;
      const before = previous[key].p95_ms;
      const delta = now === null || before === null ? null : now - before;
      return { tool: key, current: now, previous: before, delta, trend: trendOf(delta, true) };
    });
}

/** p95 por tool nas duas cargas (só as tools presentes nas duas). */
export function compareToolP95(current: LoadRun, previous: LoadRun): ToolDelta[] {
  return compareP95(current.per_tool, previous.per_tool);
}

/** p95 por caso nas duas cargas do agente (só os casos presentes nas duas). */
export function compareCaseP95(current: AgentLoadRun, previous: AgentLoadRun): ToolDelta[] {
  return compareP95(current.per_case, previous.per_case);
}

const CONFIG_LABELS: Array<[keyof LoadConfigRecord, string]> = [
  ["concurrency", "sessões simultâneas"],
  ["duration_seconds", "duração"],
  ["iterations", "iterações"],
  ["tools", "tools"],
  ["timeout_seconds", "timeout"],
];

const AGENT_CONFIG_LABELS: Array<[keyof AgentConfigRecord, string]> = [
  ["provider", "provedor"],
  ["concurrency", "sessões simultâneas"],
  ["duration_seconds", "duração"],
  ["iterations", "iterações"],
  ["selection", "seleção de casos"],
  ["timeout_seconds", "timeout"],
];

function differing<T extends object>(a: T, b: T, labels: Array<[keyof T, string]>): string[] {
  return labels
    .filter(([key]) => JSON.stringify(a[key] ?? null) !== JSON.stringify(b[key] ?? null))
    .map(([, label]) => label);
}

/** Parâmetros que diferem entre as duas cargas do mesmo modo; vazio = comparação direta. */
export function configDifferences(
  a: LoadConfigRecord | AgentConfigRecord,
  b: LoadConfigRecord | AgentConfigRecord,
): string[] {
  if (a.mode === "agent" && b.mode === "agent") return differing(a, b, AGENT_CONFIG_LABELS);
  if (a.mode !== "agent" && b.mode !== "agent") return differing(a, b, CONFIG_LABELS);
  return ["modo"];
}
