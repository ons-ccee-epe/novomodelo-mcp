import { Link } from "react-router-dom";

import { deltaPp, passRate, type Reference } from "@/shared/comparison";
import { historyBatchPath } from "@/shared/constants/Routes";
import { conjuntoOf } from "@/shared/conjunto";
import type { BatchResult } from "@/shared/types";
import { ConjuntoTag } from "./ConjuntoTag";

interface Props {
  batch: BatchResult;
  reference: Reference | null;
  selected: boolean;
  isBaseline: boolean;
  canToggle: boolean;
  onToggleBaseline: () => void;
}

const pad = (n: number) => String(n).padStart(2, "0");

function formatDate(timestamp: string): string {
  const d = new Date(timestamp);
  if (Number.isNaN(d.getTime())) return timestamp;
  return `${pad(d.getDate())}/${pad(d.getMonth() + 1)} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

const decimal = (n: number) => n.toFixed(1).replace(".", ",");

function formatDelta(delta: number | null): { text: string; trend: "up" | "down" | "none" } {
  if (delta === null) return { text: "—", trend: "none" };
  const rounded = Math.round(delta * 10) / 10;
  if (rounded === 0) return { text: "▲ +0,0 pp", trend: "none" };
  if (rounded > 0) return { text: `▲ +${decimal(rounded)} pp`, trend: "up" };
  return { text: `▼ −${decimal(-rounded)} pp`, trend: "down" };
}

export function BatchCard({
  batch,
  reference,
  selected,
  isBaseline,
  canToggle,
  onToggleBaseline,
}: Props) {
  const rate = passRate(batch);
  const pct = rate === null ? "—" : `${decimal(rate)}%`;
  const delta = formatDelta(reference ? deltaPp(batch, reference.batch) : null);
  const deltaTitle = reference ? `vs ${reference.kind} ${reference.batch.batch_id}` : undefined;
  const starLabel = isBaseline
    ? `Remover baseline ${batch.batch_id}`
    : `Definir como baseline ${batch.batch_id}`;

  return (
    <li
      className="cobre-batch-card"
      data-batch-id={batch.batch_id}
      aria-current={selected ? "true" : undefined}
    >
      <Link className="cobre-batch-link" to={historyBatchPath(batch.batch_id)}>
        {formatDate(batch.timestamp)}
      </Link>
      <ConjuntoTag conjunto={conjuntoOf(batch)} />
      <button
        type="button"
        className="cobre-star"
        aria-label={starLabel}
        aria-pressed={isBaseline}
        disabled={!canToggle}
        title={canToggle ? starLabel : "Suba o launcher para alterar a baseline"}
        onClick={onToggleBaseline}
      >
        {isBaseline ? "★" : "☆"}
      </button>
      <span className="cobre-batch-counts">
        {batch.passed}/{batch.total_tests} aprovadas · {pct}
      </span>
      <span className="cobre-delta" data-trend={delta.trend} title={deltaTitle}>
        {delta.text}
      </span>
    </li>
  );
}
