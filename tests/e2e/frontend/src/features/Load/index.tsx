import { useLoadLauncher } from "@/services/api/useLoadLauncher";
import { useLoadResults } from "@/services/api/useLoadResults";
import { isAgentRun } from "@/shared/types";
import { fmtLoadId } from "./format";
import { AgentCaseTable } from "./components/AgentCaseTable";
import { AgentDetails } from "./components/AgentDetails";
import { AgentSummaryCards } from "./components/AgentSummaryCards";
import { LoadCharts } from "./components/LoadCharts";
import { LoadComparison } from "./components/LoadComparison";
import { LoadDetails } from "./components/LoadDetails";
import { LoadLauncher } from "./components/LoadLauncher";
import { LoadPerToolChart } from "./components/LoadPerToolChart";
import { LoadProgress } from "./components/LoadProgress";
import { LoadRunSelector } from "./components/LoadRunSelector";
import { LoadSummaryCards } from "./components/LoadSummaryCards";
import { LoadToolTable } from "./components/LoadToolTable";

/** Área "Carga": dispara e acompanha testes de carga e mostra as cargas gravadas. */
export function Load() {
  const d = useLoadResults();
  const launcher = useLoadLauncher(d.showNewest);
  const run = d.run;

  return (
    <div className="cobre-shell">
      {launcher.run && (launcher.busy || launcher.run.status !== "pending") && (
        <LoadProgress run={launcher.run} stopping={launcher.stopping} onStop={launcher.stop} />
      )}

      <h1><repositório anterior> — Teste de carga</h1>
      <p className="cobre-muted">
        Cada sessão simultânea tem o seu próprio servidor MCP. Nas tools diretas, as sessões chamam
        só tools somente leitura, sem LLM, e a subida dos servidores é medida à parte, fora da
        latência. Nos casos por agente, as sessões rodam em laço os casos do cases.yaml num
        provedor de IA (consome tokens), e a latência é a do caso inteiro, com a subida do agente.
      </p>

      <LoadLauncher launcher={launcher} />

      {d.error && (
        <div className="cobre-banner" data-kind="critical">
          Erro ao carregar as cargas gravadas: {d.error}
          <div className="cobre-banner-note">
            Verifique se o dev server serve <code>/data/results/load/</code>.
          </div>
        </div>
      )}

      {d.loading && d.runs.length === 0 && !d.error && (
        <div className="cobre-muted">Carregando cargas gravadas…</div>
      )}

      {!d.loading && d.runs.length === 0 && !d.error && (
        <div className="cobre-no-data">
          Nenhuma carga gravada ainda. Dispare uma acima, ou rode{" "}
          <code>python -m tests.e2e.load.run --concurrency 2 --duration 10</code>.
        </div>
      )}

      {d.runs.length > 0 && (
        <>
          <LoadRunSelector
            runs={d.runs}
            selectedId={d.selectedId}
            compareId={d.compareId}
            onSelect={d.selectRun}
            onCompare={d.selectCompare}
            onReload={d.reload}
          />

          {run ? (
            <>
              <p className="cobre-muted">
                Carga <strong>{run.load_id}</strong> ({fmtLoadId(run.load_id)}) · ambiente{" "}
                {run.environment} · versão {run.version}
                {isAgentRun(run) ? ` · agente ${run.agent.label}` : ""}
              </p>
              {isAgentRun(run) ? <AgentSummaryCards run={run} /> : <LoadSummaryCards run={run} />}
              {d.compareRun && <LoadComparison current={run} previous={d.compareRun} />}
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
                <h2 className="cobre-section-title">{isAgentRun(run) ? "Por caso" : "Por tool"}</h2>
                <LoadPerToolChart run={run} />
                {isAgentRun(run) ? (
                  <AgentCaseTable perCase={run.per_case} />
                ) : (
                  <LoadToolTable perTool={run.per_tool} />
                )}
              </section>
              {isAgentRun(run) ? <AgentDetails run={run} /> : <LoadDetails run={run} />}
            </>
          ) : (
            <div className="cobre-muted">Carregando a carga selecionada…</div>
          )}
        </>
      )}
    </div>
  );
}
