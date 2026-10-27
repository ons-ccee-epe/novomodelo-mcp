import { Link } from "react-router-dom";

import { deltaPp, passRate, type Reference } from "@/shared/comparison";
import { historyBatchPath } from "@/shared/constants/Routes";
import type { BatchResult } from "@/shared/types";
import { formatDate, formatDelta, formatDuration, rateBand } from "../format";
import { ConjuntoTag } from "./ConjuntoTag";

interface Props {
  batch: BatchResult;
  reference: Reference | null;
  selected: boolean;
  isBaseline: boolean;
}

/** Soma das latências: as perguntas rodam em sequência, então é o tempo da bateria. */
export function batchDurationMs(batch: BatchResult): number {
  return batch.test_results.reduce((sum, r) => sum + r.latency_ms, 0);
}

export function BatchCard({ batch, reference, selected, isBaseline }: Props) {
  const rate = passRate(batch);
  const delta = formatDelta(reference ? deltaPp(batch, reference.batch) : null);
  const deltaTitle = reference ? `vs ${reference.kind} ${reference.batch.batch_id}` : undefined;

  return (
    <li
      className="cobre-batch-card"
      data-batch-id={batch.batch_id}
      aria-current={selected ? "true" : undefined}
    >
      <Link className="cobre-batch-link" to={historyBatchPath(batch.batch_id)}>
        {formatDate(batch.timestamp)}
      </Link>
      <span className="cobre-batch-tags">
        <ConjuntoTag batch={batch} />
        {isBaseline && (
          <span className="cobre-pill" data-tone="baseline">
            Baseline
          </span>
        )}
      </span>
      <span className="cobre-batch-counts">
        {batch.passed}/{batch.total_tests} · {formatDuration(batchDurationMs(batch))}
      </span>
      <span className="cobre-rate" data-band={rateBand(rate)}>
        {rate === null ? "—" : `${Math.round(rate)}%`}
      </span>
      <span className="cobre-delta-box" data-trend={delta.trend} title={deltaTitle}>
        {delta.text}
      </span>
    </li>
  );
}
