import type { ReactNode } from "react";

import { deltaPp, passRate, type Reference } from "@/shared/comparison";
import type { BatchResult } from "@/shared/types";
import { decimal, formatDelta, formatDuration, rateBand } from "../format";
import { ConjuntoTag } from "./ConjuntoTag";

const SHORT_SHA_CHARS = 7;

/** Soma das latências: as perguntas rodam em sequência, então é o tempo da bateria. */
export function batchDurationMs(batch: BatchResult): number {
  return batch.test_results.reduce((sum, r) => sum + r.latency_ms, 0);
}

interface Props {
  batch: BatchResult;
  reference: Reference | null;
}

const ms = (v: number | undefined) => (typeof v === "number" ? `${Math.round(v)} ms` : "—");

/** Um par rótulo/valor; data-stat marca o que entra no PNG do resumo. */
function Stat({
  label,
  value,
  title,
  wide = false,
}: {
  label: string;
  value: ReactNode;
  title?: string;
  wide?: boolean;
}) {
  return (
    <div data-stat aria-label={label} title={title} data-wide={wide || undefined}>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

/** Resumo da bateria: a aprovação em destaque e os dados da rodada. */
export function BatchOverview({ batch, reference }: Props) {
  const rate = passRate(batch);
  const delta = formatDelta(reference ? deltaPp(batch, reference.batch) : null);
  const version =
    batch.mcp_version && batch.mcp_version !== "unknown"
      ? `v${batch.mcp_version}`
      : "—";

  return (
    <section className="nm-panel nm-batch-overview" aria-label="Resumo da bateria">
      <div className="nm-batch-overview-rate" data-stat aria-label="Aprovação">
        <span className="nm-rate" data-band={rateBand(rate)}>
          {rate === null ? "—" : `${decimal(rate)}%`}
        </span>
        <span className="nm-card-label">Aprovação</span>
      </div>
      <dl className="nm-stats">
        <Stat label="Perguntas" value={`${batch.passed}/${batch.total_tests} aprovadas`} />
        <Stat
          label="Δ vs referência"
          title={reference ? `vs ${reference.kind} ${reference.batch.batch_id}` : undefined}
          value={
            <span className="nm-delta" data-trend={delta.trend}>
              {delta.text}
            </span>
          }
        />
        <Stat label="Tempo total" value={formatDuration(batchDurationMs(batch))} />
        <Stat label="Conjunto" wide value={<ConjuntoTag batch={batch} />} />
        <Stat label="Versão do MCP" value={version} />
        <Stat
          label="Commit"
          title={batch.git_commit_sha || undefined}
          value={
            batch.git_commit_sha ? (
              <code>{batch.git_commit_sha.slice(0, SHORT_SHA_CHARS)}</code>
            ) : (
              "—"
            )
          }
        />
      </dl>
    </section>
  );
}

/** Placar por status e tempos da bateria. */
export function BatchStats({ batch }: { batch: BatchResult }) {
  const m = batch.metrics;
  const latencies = batch.test_results.map((r) => r.latency_ms);
  return (
    <div className="nm-batch-panels">
      <section className="nm-panel" aria-label="Resultado">
        <h3 className="nm-panel-title">Resultado</h3>
        <dl className="nm-stats">
          <Stat label="Aprovadas" value={batch.passed} />
          <Stat label="Parciais" value={batch.partial} />
          <Stat label="Falhas" value={batch.failed} />
          <Stat label="Timeout" value={batch.timeout} />
          <Stat label="Erro de infra" value={batch.erro_infra ?? 0} />
          <Stat label="Puladas" value={batch.skipped} />
        </dl>
      </section>
      <section className="nm-panel" aria-label="Tempos">
        <h3 className="nm-panel-title">Tempos</h3>
        <dl className="nm-stats">
          <Stat label="Latência média" value={ms(m?.avg_latency_ms)} />
          <Stat label="Latência p95" value={ms(m?.p95_latency_ms)} />
          <Stat label="Mínima" value={ms(latencies.length ? Math.min(...latencies) : undefined)} />
          <Stat label="Máxima" value={ms(latencies.length ? Math.max(...latencies) : undefined)} />
        </dl>
      </section>
    </div>
  );
}
