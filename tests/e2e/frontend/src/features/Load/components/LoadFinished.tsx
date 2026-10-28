import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { fetchLoadRun, type LoadRunState } from "@/services/loadApi";
import { historyLoadPath } from "@/shared/constants/Routes";
import { isAgentRun, type SavedLoadRun } from "@/shared/types";
import { fmtCpm, fmtMs, fmtPercent, fmtRate } from "../format";

/** Ao fim de uma carga gravada, leva ao dashboard dela no Histórico. */
export function LoadFinished({ run }: { run: LoadRunState }) {
  const navigate = useNavigate();
  const loadId = run.load_id;
  if (run.status !== "done" || !loadId) return null;

  return (
    <button
      type="button"
      className="nm-btn nm-btn-primary nm-btn-sm"
      onClick={() => navigate(historyLoadPath(loadId))}
    >
      Ver no Histórico
    </button>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <span>
      <span className="nm-muted">{label}</span> {value}
    </span>
  );
}

/** Os números principais da carga gravada; o restante fica no Histórico. */
export function LoadDoneSummary({ loadId }: { loadId: string }) {
  const [saved, setSaved] = useState<SavedLoadRun | null>(null);

  useEffect(() => {
    let alive = true;
    fetchLoadRun(loadId)
      .then((r) => alive && setSaved(r))
      .catch(() => alive && setSaved(null));
    return () => {
      alive = false;
    };
  }, [loadId]);

  if (!saved) return null;
  const t = saved.totals;

  return (
    <div className="nm-load-live" aria-label="Resumo da carga concluída">
      {isAgentRun(saved) ? (
        <>
          <Metric label="Execuções" value={String(saved.totals.calls)} />
          <Metric label="Aprovação" value={fmtPercent(saved.totals.pass_rate)} />
          <Metric label="Vazão" value={fmtCpm(saved.totals.throughput_cpm)} />
        </>
      ) : (
        <>
          <Metric label="Chamadas" value={String(t.calls)} />
          <Metric label="Vazão" value={fmtRate(t.throughput_cps)} />
        </>
      )}
      <Metric label="Taxa de erro" value={fmtPercent(t.error_rate)} />
      <Metric label="p50" value={fmtMs(t.p50_ms)} />
      <Metric label="p95" value={fmtMs(t.p95_ms)} />
      <Metric label="p99" value={fmtMs(t.p99_ms)} />
    </div>
  );
}
