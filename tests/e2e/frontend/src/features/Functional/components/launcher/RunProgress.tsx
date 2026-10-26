import { isFinished, type RunState, type RunStatus } from "@/services/launcherApi";

const STATUS_LABEL: Record<RunStatus, string> = {
  pending: "Preparando…",
  running: "Rodando…",
  done: "Concluído",
  error: "Erro",
  cancelled: "Parado",
};

interface Props {
  run: RunState;
  stopping: boolean;
  onStop: () => void;
}

function statusLabel(run: RunState, stopping: boolean): string {
  if (stopping && !isFinished(run.status)) return "Parando…";
  if (run.status === "cancelled") {
    return `Parado em ${run.completed}/${run.total} — bateria não gravada`;
  }
  return STATUS_LABEL[run.status];
}

/** Progresso agregado do run em andamento, com o botão de parar. */
export function RunProgress({ run, stopping, onStop }: Props) {
  const pct = run.total ? (run.completed / run.total) * 100 : 0;
  const active = !isFinished(run.status);
  return (
    <div className="cobre-launcher-progress" data-status={run.status}>
      <div className="cobre-progress-head">
        <strong>{statusLabel(run, stopping)}</strong>
        <span className="cobre-progress-actions">
          <span className="cobre-muted">
            {run.completed}/{run.total || "?"}
            {run.current ? ` · ${run.current}` : ""}
            {run.provider ? ` · ${run.provider}` : ""}
          </span>
          {active && (
            <button
              type="button"
              className="cobre-btn cobre-btn-danger"
              onClick={onStop}
              disabled={stopping}
              title="Interrompe o teste em andamento e não roda os restantes"
            >
              ■ Parar
            </button>
          )}
        </span>
      </div>
      <div className="cobre-progress-bar" aria-hidden>
        <div className="cobre-progress-fill" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
