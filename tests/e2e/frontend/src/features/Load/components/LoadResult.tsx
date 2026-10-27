import type { LoadResultsData } from "@/services/api/useLoadResults";
import { isAgentRun, type SavedLoadRun } from "@/shared/types";
import { fmtLoadId } from "../format";
import { AgentCaseTable } from "./AgentCaseTable";
import { AgentDetails } from "./AgentDetails";
import { AgentSummaryCards } from "./AgentSummaryCards";
import { LoadCharts } from "./LoadCharts";
import { LoadCompareSelect } from "./LoadCompareSelect";
import { LoadComparison } from "./LoadComparison";
import { LoadDetails } from "./LoadDetails";
import { LoadPerToolChart } from "./LoadPerToolChart";
import { LoadSummaryCards } from "./LoadSummaryCards";
import { LoadToolTable } from "./LoadToolTable";

/** Dashboard de uma carga gravada: resumo, comparação, gráficos, por tool/caso e detalhes. */
export function LoadResult({ run, data }: { run: SavedLoadRun; data: LoadResultsData }) {
  const agent = isAgentRun(run);

  return (
    <article className="cobre-load-result" aria-label="Resultado da carga">
      <header className="cobre-load-result-head">
        <h2>
          {agent ? "Carga do agente" : "Carga de tools"} — {fmtLoadId(run.load_id)}
        </h2>
        <p className="cobre-muted cobre-load-meta">
          <code>{run.load_id}</code> · ambiente {run.environment} · versão {run.version}
          {isAgentRun(run) ? ` · agente ${run.agent.label}` : ""}
        </p>
      </header>

      {isAgentRun(run) ? <AgentSummaryCards run={run} /> : <LoadSummaryCards run={run} />}

      <section className="cobre-section">
        <LoadCompareSelect
          runs={data.runs}
          selectedId={data.selectedId}
          compareId={data.compareId}
          onCompare={data.selectCompare}
        />
        {data.compareRun && <LoadComparison current={run} previous={data.compareRun} />}
      </section>

      <section className="cobre-section">
        <h2 className="cobre-section-title">Ao longo do tempo</h2>
        {isAgentRun(run) ? (
          <LoadCharts
            series={run.series}
            durationSeconds={run.duration_seconds}
            fileStem={run.load_id}
            throughput={{
              title: `Casos concluídos por bucket de ${run.series_bucket_seconds} s`,
              ok: "concluídos",
              failed: "erros e timeouts",
            }}
          />
        ) : (
          <LoadCharts
            series={run.series}
            durationSeconds={run.duration_seconds}
            fileStem={run.load_id}
          />
        )}
      </section>

      <section className="cobre-section">
        <h2 className="cobre-section-title">{agent ? "Por caso" : "Por tool"}</h2>
        <LoadPerToolChart run={run} />
        {isAgentRun(run) ? (
          <AgentCaseTable perCase={run.per_case} />
        ) : (
          <LoadToolTable perTool={run.per_tool} />
        )}
      </section>

      {isAgentRun(run) ? <AgentDetails run={run} /> : <LoadDetails run={run} />}
    </article>
  );
}
