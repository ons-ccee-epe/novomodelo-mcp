import { deltaPp, passRate, type Reference } from "@/shared/comparison";
import type { BatchResult } from "@/shared/types";
import { decimal, formatDelta } from "../format";

interface Props {
  batch: BatchResult;
  reference: Reference | null;
}

const ms = (v: number | undefined) => (typeof v === "number" ? `${Math.round(v)} ms` : "—");

export function BatchCards({ batch, reference }: Props) {
  const rate = passRate(batch);
  const delta = formatDelta(reference ? deltaPp(batch, reference.batch) : null);
  const m = batch.metrics;
  return (
    <div className="cobre-summary">
      <div className="cobre-card" aria-label="Total">
        <div className="cobre-card-value">{batch.total_tests}</div>
        <div className="cobre-card-label">Total</div>
      </div>
      <div className="cobre-card" data-accent="pass" aria-label="Aprovação">
        <div className="cobre-card-value">{rate === null ? "—" : `${decimal(rate)}%`}</div>
        <div className="cobre-card-label">Aprovação</div>
      </div>
      <div className="cobre-card" data-accent="rate" aria-label="Δ vs referência">
        <div
          className="cobre-card-value cobre-delta"
          data-trend={delta.trend}
          title={reference ? `vs ${reference.kind} ${reference.batch.batch_id}` : undefined}
        >
          {delta.text}
        </div>
        <div className="cobre-card-label">Δ vs referência</div>
      </div>
      <div className="cobre-card" data-accent="time" aria-label="Latência média">
        <div className="cobre-card-value">{ms(m?.avg_latency_ms)}</div>
        <div className="cobre-card-label">Latência média</div>
      </div>
      <div className="cobre-card" data-accent="time" aria-label="Latência p95">
        <div className="cobre-card-value">{ms(m?.p95_latency_ms)}</div>
        <div className="cobre-card-label">Latência p95</div>
      </div>
    </div>
  );
}
