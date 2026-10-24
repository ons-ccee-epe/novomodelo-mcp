import { isFinished } from "@/services/launcherApi";
import type { LoadRunState } from "@/services/loadApi";
import { fmtMs, fmtPercent, fmtRate, fmtSeconds } from "../format";
import { LoadCharts } from "./LoadCharts";

interface Props {
  run: LoadRunState;
  stopping: boolean;
  onStop: () => void;
}

const PHASE_LABEL: Record<string, string> = {
  preflight: "Validando o mix (pré-voo)…",
  running: "Carga em andamento…",
  finishing: "Encerrando os clientes…",
};

function headline(run: LoadRunState, stopping: boolean): string {
  if (stopping && !isFinished(run.status)) return "Parando…";
  if (run.status === "done") return "Concluída";
  if (run.status === "error") return "Erro";
  if (run.status === "cancelled") return "Parada — carga não gravada";
  if (run.phase === "starting") {
    const clients = run.progress?.clients;
    return clients
      ? `Subindo os servidores (${clients.ready}/${clients.requested})…`
      : "Subindo os servidores…";
  }
  return (run.phase && PHASE_LABEL[run.phase]) || "Preparando…";
}

/** Progresso ao vivo da carga: fase, contadores, gráfico recente e o botão de parar. */
export function LoadProgress({ run, stopping, onStop }: Props) {
  const progress = run.progress;
  const active = !isFinished(run.status);
  const pct =
    progress && progress.duration_seconds > 0
      ? Math.min((progress.elapsed_seconds / progress.duration_seconds) * 100, 100)
      : 0;

  return (
    <div className="cobre-launcher-progress" data-status={run.status}>
      <div className="cobre-progress-head">
        <strong>{headline(run, stopping)}</strong>
        <span className="cobre-progress-actions">
          <span className="cobre-muted">
            {run.config.concurrency} cliente(s) · {run.config.duration_seconds} s
            {progress && progress.phase === "running"
              ? ` · ${fmtSeconds(progress.elapsed_seconds)} decorridos`
              : ""}
          </span>
          {active && (
            <button
              type="button"
              className="cobre-btn cobre-btn-danger"
              onClick={onStop}
              disabled={stopping}
              title="Encerra todos os servidores MCP da carga; nada é gravado"
            >
              ■ Parar
            </button>
          )}
        </span>
      </div>
      <div className="cobre-progress-bar" aria-hidden>
        <div className="cobre-progress-fill" style={{ width: `${pct}%` }} />
      </div>

      {progress && progress.calls > 0 && (
        <div className="cobre-load-live" aria-label="Métricas ao vivo">
          <span>
            <span className="cobre-muted">Chamadas</span> {progress.calls}
          </span>
          <span>
            <span className="cobre-muted">Vazão</span> {fmtRate(progress.throughput_cps)}
          </span>
          <span>
            <span className="cobre-muted">Taxa de erro</span> {fmtPercent(progress.error_rate)}
          </span>
          <span>
            <span className="cobre-muted">p50</span> {fmtMs(progress.p50_ms)}
          </span>
          <span>
            <span className="cobre-muted">p95</span> {fmtMs(progress.p95_ms)}
          </span>
          {progress.clients.respawns > 0 && (
            <span>
              <span className="cobre-muted">Clientes recriados</span> {progress.clients.respawns}
            </span>
          )}
        </div>
      )}

      {progress && progress.series.length > 0 && active && (
        <LoadCharts series={progress.series} compact />
      )}
      {run.status === "error" && run.error && (
        <div className="cobre-banner cobre-banner-stacked" data-kind="critical">
          {run.error}
        </div>
      )}
    </div>
  );
}
