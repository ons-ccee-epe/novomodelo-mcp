import { useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { MetricsHistoryRecord } from "@/shared/types";

interface Props {
  history: MetricsHistoryRecord[];
  baseline: {
    pct_mcp_used?: number;
    pct_correct_tool?: number;
    pct_correct_result?: number;
    avg_latency_ms?: number;
  } | null;
}

type Period = 5 | 10 | 20 | "all";

const PERIODS: Period[] = [5, 10, 20, "all"];
const DEFAULT_PERIOD: Period = 20;
const CHART_HEIGHT_PX = 240;
const MAX_LABELED_POINTS = 12;
const BATCH_LABEL_CHARS = 15;

const SERIES: Array<{
  key: keyof MetricsHistoryRecord;
  title: string;
  color: string;
  baselineKey: keyof NonNullable<Props["baseline"]>;
  help: string;
}> = [
  {
    key: "pct_mcp_used",
    title: "MCP Usage (%)",
    color: "var(--cobre-chart-mcp)",
    baselineKey: "pct_mcp_used",
    help: "Percentual de testes em que o agente chamou pelo menos uma tool do MCP novomodelo quando deveria. Mede se o provedor de IA está de fato usando o MCP (e não respondendo sozinho).",
  },
  {
    key: "pct_correct_tool",
    title: "Correct Tool (%)",
    color: "var(--cobre-chart-tool)",
    baselineKey: "pct_correct_tool",
    help: "Percentual de testes em que o agente escolheu a tool MCP esperada para a pergunta (ex.: 'resuma o caso' → case_summary). Mede o roteamento pergunta → tool.",
  },
  {
    key: "pct_correct_result",
    title: "Correct Result (%)",
    color: "var(--cobre-chart-result)",
    baselineKey: "pct_correct_result",
    help: "Percentual de testes em que o resultado da tool passou em todas as validações do caso (status, conteúdo do envelope, keywords). Mede se a tool devolveu o que se esperava.",
  },
  {
    key: "avg_latency_ms",
    title: "Average Latency (ms)",
    color: "var(--cobre-chart-latency)",
    baselineKey: "avg_latency_ms",
    help: "Tempo médio, em milissegundos, do início do prompt até o fim da execução do caso (inclui o raciocínio do provedor + a chamada da tool). Menor é melhor.",
  },
];

const TREND_HELP =
  "Cada gráfico mostra a evolução de uma métrica ao longo das baterias (eixo X = baterias, da mais antiga à mais recente). A linha tracejada é o baseline de referência. Passe o mouse no título de cada gráfico para a definição da métrica.";

/** Graficos de tendencia por metrica, com janela selecionavel e baseline. */
export function TrendCharts({ history, baseline }: Props) {
  const [period, setPeriod] = useState<Period>(DEFAULT_PERIOD);

  const data = useMemo(() => {
    const rows = history.map((h) => ({
      label: (h.batch_id ?? "").slice(0, BATCH_LABEL_CHARS),
      pct_mcp_used: h.pct_mcp_used,
      pct_correct_tool: h.pct_correct_tool,
      pct_correct_result: h.pct_correct_result,
      avg_latency_ms: h.avg_latency_ms,
    }));
    if (period === "all") return rows;
    return rows.slice(Math.max(0, rows.length - period));
  }, [history, period]);

  if (history.length === 0) {
    return (
      <section className="cobre-section">
        <h2 className="cobre-section-title">Tendências</h2>
        <div className="cobre-no-data">Nenhum histórico de métricas disponível</div>
      </section>
    );
  }

  return (
    <section className="cobre-section">
      <h2 className="cobre-section-title">
        Tendências
        <span
          className="cobre-info-icon"
          tabIndex={0}
          role="img"
          aria-label={TREND_HELP}
          title={TREND_HELP}
        >
          ⓘ
        </span>
        <span className="cobre-period-group">
          {PERIODS.map((p) => (
            <button
              key={String(p)}
              type="button"
              onClick={() => setPeriod(p)}
              className="cobre-period-btn"
              data-active={p === period}
              aria-pressed={p === period}
            >
              {p === "all" ? "Todas" : p}
            </button>
          ))}
        </span>
      </h2>
      <div className="cobre-charts">
        {SERIES.map((s) => {
          const baseValue = baseline?.[s.baselineKey];
          return (
            <div key={s.key} className="cobre-chart">
              <div className="cobre-chart-title" title={s.help}>
                {s.title}
                <span className="cobre-info-icon" aria-label={s.help} title={s.help}>
                  ⓘ
                </span>
              </div>
              <ResponsiveContainer width="100%" height={CHART_HEIGHT_PX}>
                <LineChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--cobre-border)" />
                  <XAxis dataKey="label" tick={{ fontSize: 10 }} hide={data.length > MAX_LABELED_POINTS} />
                  <YAxis tick={{ fontSize: 10 }} width={44} />
                  <Tooltip />
                  <Line
                    type="monotone"
                    dataKey={s.key}
                    stroke={s.color}
                    strokeWidth={2}
                    dot={false}
                  />
                  {typeof baseValue === "number" && (
                    <ReferenceLine
                      y={baseValue}
                      stroke="var(--cobre-skip)"
                      strokeDasharray="5 5"
                      label={{ value: `baseline ${baseValue.toFixed(1)}`, fontSize: 10 }}
                    />
                  )}
                </LineChart>
              </ResponsiveContainer>
            </div>
          );
        })}
      </div>
    </section>
  );
}
