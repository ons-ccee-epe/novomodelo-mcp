import type { ReactNode } from "react";

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
  /** Ação ao lado do contador quando a rodada termina (ver resultados). */
  action?: ReactNode;
}

function statusLabel(run: RunState, stopping: boolean): string {
  if (stopping && !isFinished(run.status)) return "Parando…";
  if (run.status === "cancelled") {
    return `Parado em ${run.completed}/${run.total} — bateria não gravada`;
  }
  return STATUS_LABEL[run.status];
}

/** Progresso agregado do run em andamento, com o botão de parar. */
export function RunProgress({ run, stopping, onStop, action }: Props) {
  const pct = run.total ? (run.completed / run.total) * 100 : 0;
  const active = !isFinished(run.status);
  return (
    <div className="nm-launcher-progress" data-status={run.status}>
      <div className="nm-progress-head">
        <strong>{statusLabel(run, stopping)}</strong>
        <span className="nm-progress-actions">
          <span className="nm-muted">
            {run.completed}/{run.total || "?"}
            {run.current ? ` · ${run.current}` : ""}
            {run.provider ? ` · ${run.provider}` : ""}
          </span>
          {active && (
            <button
              type="button"
              className="nm-btn nm-btn-danger"
              onClick={onStop}
              disabled={stopping}
              title="Interrompe o teste em andamento e não roda os restantes"
            >
              ■ Parar
            </button>
          )}
          {action}
        </span>
      </div>
      <div className="nm-progress-bar" aria-hidden>
        <div className="nm-progress-fill" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
