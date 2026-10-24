import { useLoadLauncher } from "@/services/api/useLoadLauncher";
import { useLoadResults } from "@/services/api/useLoadResults";
import { fmtLoadId } from "./format";
import { LoadCharts } from "./components/LoadCharts";
import { LoadComparison } from "./components/LoadComparison";
import { LoadDetails } from "./components/LoadDetails";
import { LoadLauncher } from "./components/LoadLauncher";
import { LoadRunSelector } from "./components/LoadRunSelector";
import { LoadSummaryCards } from "./components/LoadSummaryCards";
import { LoadToolTable } from "./components/LoadToolTable";

/** Área "Carga": dispara e acompanha testes de carga e mostra as cargas gravadas. */
export function Load() {
  const d = useLoadResults();
  const launcher = useLoadLauncher(d.showNewest);

  return (
    <div className="cobre-shell">
      <h1><repositório anterior> — Teste de carga</h1>
      <p className="cobre-muted">
        N clientes, cada um com o seu próprio servidor MCP, chamam só tools somente leitura. A
        subida dos servidores é medida à parte e não entra na latência.
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

          {d.run ? (
            <>
              <p className="cobre-muted">
                Carga <strong>{d.run.load_id}</strong> ({fmtLoadId(d.run.load_id)}) · ambiente{" "}
                {d.run.environment} · versão {d.run.version}
              </p>
              <LoadSummaryCards run={d.run} />
              {d.compareRun && <LoadComparison current={d.run} previous={d.compareRun} />}
              <section className="cobre-section">
                <h2 className="cobre-section-title">Ao longo do tempo</h2>
                <LoadCharts series={d.run.series} durationSeconds={d.run.duration_seconds} />
              </section>
              <section className="cobre-section">
                <h2 className="cobre-section-title">Por tool</h2>
                <LoadToolTable perTool={d.run.per_tool} />
              </section>
              <LoadDetails run={d.run} />
            </>
          ) : (
            <div className="cobre-muted">Carregando a carga selecionada…</div>
          )}
        </>
      )}
    </div>
  );
}
