import type { ReactNode } from "react";

import { isFinished } from "@/services/launcherApi";
import {
  isAgentProgress,
  type AgentLoadProgress,
  type LoadRunState,
  type ToolsLoadProgress,
} from "@/services/loadApi";
import { fmtCpm, fmtMs, fmtPercent, fmtRate, fmtSeconds } from "../format";
import { LoadCharts } from "./LoadCharts";

interface Props {
  run: LoadRunState;
  stopping: boolean;
  onStop: () => void;
  /** Ação ao lado do cabeçalho quando a carga termina (ex.: abrir o resultado). */
  action?: ReactNode;
  /** Resumo que substitui as métricas ao vivo quando a carga termina gravada. */
  summary?: ReactNode;
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
  const progress = run.progress;
  if (run.config.mode === "agent") {
    return agentHeadline(run, progress && isAgentProgress(progress) ? progress : null);
  }
  if (run.phase === "starting") {
    const clients = progress?.clients;
    return clients
      ? `Abrindo as sessões (${clients.ready}/${clients.requested})…`
      : "Subindo os servidores…";
  }
  return (run.phase && PHASE_LABEL[run.phase]) || "Preparando…";
}

function agentHeadline(run: LoadRunState, progress: AgentLoadProgress | null): string {
  switch (run.phase) {
    case "preflight":
      return "Pré-voo: casos e servidor MCP (sem tokens)…";
    case "starting":
      return progress
        ? `Abrindo as sessões (${progress.sessions.ready}/${progress.sessions.requested})…`
        : "Subindo os agentes…";
    case "running":
      return "Carga em andamento…";
    case "finishing":
      return `Aguardando ${progress?.in_flight.length ?? 0} caso(s) em curso…`;
    default:
      return "Preparando…";
  }
}

function Metric({ label, children }: { label: string; children: ReactNode }) {
  return (
    <span>
      <span className="nm-muted">{label}</span> {children}
    </span>
  );
}

function ToolsLive({ progress }: { progress: ToolsLoadProgress }) {
  return (
    <div className="nm-load-live" aria-label="Métricas ao vivo">
      <span>
        <span className="nm-muted">Sessões abertas</span> {progress.clients.ready}/
        {progress.clients.requested}
      </span>
      <Metric label="Chamadas">{progress.calls}</Metric>
      <Metric label="Vazão">{fmtRate(progress.throughput_cps)}</Metric>
      <Metric label="Taxa de erro">{fmtPercent(progress.error_rate)}</Metric>
      <Metric label="p50">{fmtMs(progress.p50_ms)}</Metric>
      <Metric label="p95">{fmtMs(progress.p95_ms)}</Metric>
      {progress.clients.respawns > 0 && (
        <Metric label="Sessões recriadas">{progress.clients.respawns}</Metric>
      )}
    </div>
  );
}

function AgentLive({ progress }: { progress: AgentLoadProgress }) {
  const s = progress.sessions;
  return (
    <>
      <div className="nm-load-live" aria-label="Métricas ao vivo">
        <Metric label="Sessões">
          {s.ready}/{s.requested} abertas · {s.running} em execução · {s.finished} concluídas
          {s.failed > 0 ? ` · ${s.failed} falharam` : ""}
        </Metric>
        <Metric label="Execuções">{progress.calls}</Metric>
        <Metric label="Aprovação">
          {progress.calls > 0 ? fmtPercent(progress.pass_rate) : "—"}
        </Metric>
        <Metric label="Vazão">{fmtCpm(progress.throughput_cpm)}</Metric>
        <Metric label="Erros e timeouts">{progress.errors + progress.timeouts}</Metric>
        <Metric label="p50">{fmtMs(progress.p50_ms)}</Metric>
        <Metric label="p95">{fmtMs(progress.p95_ms)}</Metric>
      </div>
      {progress.in_flight.length > 0 && (
        <ul className="nm-tool-call-list" aria-label="Casos em curso">
          {progress.in_flight.map((item) => (
            <li key={`${item.session}-${item.case_id}`}>
              sessão {item.session} · <code>{item.case_id}</code> ·{" "}
              {fmtSeconds(item.elapsed_seconds)}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

/** Progresso ao vivo da carga: fase, contadores, gráfico recente e o botão de parar. */
export function LoadProgress({ run, stopping, onStop, action, summary }: Props) {
  const progress = run.progress;
  const active = !isFinished(run.status);
  const agent = run.config.mode === "agent";
  const pct =
    progress && progress.duration_seconds > 0
      ? Math.min((progress.elapsed_seconds / progress.duration_seconds) * 100, 100)
      : 0;
  const agentProgress = progress && isAgentProgress(progress) ? progress : null;
  const toolsProgress = progress && !isAgentProgress(progress) ? progress : null;
  const bucket = agentProgress?.series_bucket_seconds ?? 5;
  const done = run.status === "done" && summary;
  const showLive =
    !done &&
    progress &&
    (agentProgress ? ["running", "finishing"].includes(progress.phase) : progress.calls > 0);

  return (
    <div className="nm-launcher-progress" data-status={run.status}>
      <div className="nm-progress-head">
        <strong>{headline(run, stopping)}</strong>
        <span className="nm-progress-actions">
          <span className="nm-muted">
            {run.config.mode === "agent" ? `${run.config.provider} · ` : ""}
            {run.config.concurrency} sessões simultâneas · {run.config.duration_seconds} s
            {progress && progress.phase === "running"
              ? ` · ${fmtSeconds(progress.elapsed_seconds)} decorridos`
              : ""}
          </span>
          {active && (
            <button
              type="button"
              className="nm-btn nm-btn-danger"
              onClick={onStop}
              disabled={stopping}
              title={
                agent
                  ? "Encerra os agentes e o servidor MCP da carga; nada é gravado"
                  : "Encerra todos os servidores MCP da carga; nada é gravado"
              }
            >
              ■ Parar
            </button>
          )}
          {!active && action}
        </span>
      </div>
      <div className="nm-progress-bar" aria-hidden>
        <div className="nm-progress-fill" style={{ width: `${pct}%` }} />
      </div>

      {showLive && agentProgress && <AgentLive progress={agentProgress} />}
      {showLive && toolsProgress && <ToolsLive progress={toolsProgress} />}
      {done && summary}

      {progress && progress.series.length > 0 && active && (
        <LoadCharts
          series={progress.series}
          compact
          throughput={
            agentProgress
              ? {
                  title: `Casos concluídos por bucket de ${bucket} s`,
                  ok: "concluídos",
                  failed: "erros e timeouts",
                }
              : undefined
          }
        />
      )}
      {run.status === "error" && run.error && (
        <div className="nm-banner nm-banner-stacked" data-kind="critical">
          {run.error}
        </div>
      )}
    </div>
  );
}
