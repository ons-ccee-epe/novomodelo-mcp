import { useEffect, useMemo, useState } from "react";
import { useResults } from "@/services/api/useResults";
import { BatchSelector } from "./components/BatchSelector";
import { AlertBanner } from "./components/AlertBanner";
import { SummaryCards } from "./components/SummaryCards";
import { TrendCharts } from "./components/TrendCharts";
import { ComparisonPanel } from "./components/ComparisonPanel";
import { MetricsByGroup } from "./components/MetricsByGroup";
import { MetricsByTag } from "./components/MetricsByTag";
import { TestTable } from "./components/TestTable";
import { TestLauncher } from "./components/TestLauncher";
import { useLauncher } from "@/services/api/useLauncher";
import type { BatchResult } from "@/shared/types";
import { fetchBatch } from "@/services/resultsApi";

/** Pagina unica do dashboard de resultados E2E. */
export function Dashboard() {
  const d = useResults();
  const launcher = useLauncher(d.reload);
  const [groupFilter, setGroupFilter] = useState<string | null>(null);
  const [baselineBatch, setBaselineBatch] = useState<BatchResult | null>(null);

  // Carrega a bateria baseline completa (para os alertas de correct-tool).
  useEffect(() => {
    if (!d.baselineId) {
      setBaselineBatch(null);
      return;
    }
    let alive = true;
    fetchBatch(d.baselineId)
      .then((b) => alive && setBaselineBatch(b))
      .catch(() => alive && setBaselineBatch(null));
    return () => {
      alive = false;
    };
  }, [d.baselineId]);

  const baselineMetrics = useMemo(
    () => (baselineBatch ? baselineBatch.metrics : null),
    [baselineBatch],
  );

  if (d.loading && !d.batch) {
    return <div className="cobre-shell cobre-muted">Carregando resultados…</div>;
  }

  if (d.error) {
    return (
      <div className="cobre-shell">
        <div className="cobre-banner" data-kind="critical">
          Erro ao carregar resultados: {d.error}
          <div className="cobre-banner-note">
            Verifique se há baterias em <code>tests/e2e/results/</code> e se o dev server está servindo{" "}
            <code>/data</code>.
          </div>
        </div>
      </div>
    );
  }

  if (d.batches.length === 0 || !d.batch) {
    return (
      <div className="cobre-shell">
        <h1><repositório anterior> — Dashboard de Testes E2E</h1>
        <TestLauncher launcher={launcher} />
        <div className="cobre-no-data">
          Nenhuma bateria de teste encontrada. Dispare os testes acima (esteira completa,
          por grupo, ou um caso) para gerar os primeiros resultados.
        </div>
      </div>
    );
  }

  return (
    <div className="cobre-shell">
      <h1><repositório anterior> — Dashboard de Testes E2E</h1>
      <p className="cobre-muted">
        Bateria <strong>{d.batch.batch_id}</strong> · ambiente {d.batch.environment} · versão{" "}
        {d.batch.cobre_mcp_version}
      </p>

      <TestLauncher launcher={launcher} />

      <BatchSelector
        batches={d.batches}
        selectedId={d.selectedId}
        compareId={d.compareId}
        baselineId={d.baselineId}
        onSelect={d.selectBatch}
        onCompare={d.selectCompare}
        onReload={d.reload}
      />

      <AlertBanner batch={d.batch} history={d.history} baseline={baselineBatch} />

      <SummaryCards batch={d.batch} />

      {d.compareBatch && <ComparisonPanel current={d.batch} previous={d.compareBatch} />}

      <TrendCharts history={d.history} baseline={baselineMetrics} />

      <MetricsByGroup
        batch={d.batch}
        selectedGroup={groupFilter}
        onSelectGroup={setGroupFilter}
      />

      <MetricsByTag batch={d.batch} />

      <TestTable batch={d.batch} groupFilter={groupFilter} />
    </div>
  );
}
