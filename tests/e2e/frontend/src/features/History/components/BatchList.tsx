import { useMemo, useState } from "react";

import { pickReference } from "@/shared/comparison";
import { conjuntoOf } from "@/shared/conjunto";
import type { BatchResult } from "@/shared/types";
import { BatchCard } from "./BatchCard";
import { ConjuntoTag } from "./ConjuntoTag";

interface Props {
  batches: BatchResult[];
  baselines: Record<string, string>;
  selectedId: string | null;
  canToggle: boolean;
  onToggleBaseline: (batch: BatchResult) => Promise<void>;
}

export function BatchList({ batches, baselines, selectedId, canToggle, onToggleBaseline }: Props) {
  const [filter, setFilter] = useState<string | null>(null);
  const [toggleError, setToggleError] = useState<string | null>(null);

  const conjuntos = useMemo(() => [...new Set(batches.map(conjuntoOf))], [batches]);
  const visible = filter ? batches.filter((b) => conjuntoOf(b) === filter) : batches;

  const toggle = (batch: BatchResult) => {
    setToggleError(null);
    onToggleBaseline(batch).catch((e: unknown) => {
      setToggleError(e instanceof Error ? e.message : String(e));
    });
  };

  return (
    <div className="cobre-batch-list">
      <div className="cobre-batch-filter">
        <button
          type="button"
          className="cobre-tag cobre-tag-all"
          aria-pressed={filter === null}
          onClick={() => setFilter(null)}
        >
          Todos
        </button>
        {conjuntos.map((c) => (
          <ConjuntoTag
            key={c}
            conjunto={c}
            pressed={filter === c}
            onClick={() => setFilter(filter === c ? null : c)}
          />
        ))}
      </div>
      {toggleError && (
        <p role="alert" className="cobre-run-finished-error">
          {toggleError}
        </p>
      )}
      <ul className="cobre-batch-items">
        {visible.map((b) => (
          <BatchCard
            key={b.batch_id}
            batch={b}
            reference={pickReference(b, batches, baselines)}
            selected={b.batch_id === selectedId}
            isBaseline={baselines[conjuntoOf(b)] === b.batch_id}
            canToggle={canToggle}
            onToggleBaseline={() => toggle(b)}
          />
        ))}
      </ul>
    </div>
  );
}
