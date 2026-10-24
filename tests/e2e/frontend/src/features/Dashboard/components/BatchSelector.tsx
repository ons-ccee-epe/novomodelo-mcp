import { useState } from "react";
import type { BatchIndexEntry } from "@/shared/types";

const RELOAD_FEEDBACK_MS = 700;

interface Props {
  batches: BatchIndexEntry[];
  selectedId: string | null;
  compareId: string | null;
  baselineId: string | null;
  onSelect: (id: string) => void;
  onCompare: (id: string | null) => void;
  onReload: () => void;
}

function label(b: BatchIndexEntry, baselineId: string | null): string {
  const s = b.summary;
  const total = s.total ?? 0;
  const rate = total > 0 ? Math.round((s.passed / total) * 100) : 0;
  const ts = (b.timestamp ?? "").slice(0, 16).replace("T", " ");
  const base = b.batch_id === baselineId ? " ★baseline" : "";
  return `${b.batch_id} | ${ts} | ✓${s.passed} ✗${s.failed} (${rate}%)${base}`;
}

/** Seletor de bateria principal + comparacao, e botao de recarga. */
export function BatchSelector({
  batches,
  selectedId,
  compareId,
  baselineId,
  onSelect,
  onCompare,
  onReload,
}: Props) {
  const [spinning, setSpinning] = useState(false);

  function handleReload() {
    setSpinning(true);
    onReload();
    // Feedback visível mesmo quando a recarga volta instantânea.
    window.setTimeout(() => setSpinning(false), RELOAD_FEEDBACK_MS);
  }

  return (
    <div className="cobre-topbar">
      <div className="cobre-field">
        <label htmlFor="batch-select" className="cobre-field-label">
          🔵 Bateria Principal
        </label>
        <select
          id="batch-select"
          className="cobre-select"
          value={selectedId ?? ""}
          onChange={(e) => onSelect(e.target.value)}
        >
          {batches.map((b, i) => (
            <option key={b.batch_id} value={b.batch_id}>
              {label(b, baselineId)}
              {i === 0 ? " (mais recente)" : ""}
            </option>
          ))}
        </select>
      </div>

      <div className="cobre-field">
        <label htmlFor="compare-select" className="cobre-field-label">
          🟡 Comparar com
        </label>
        <select
          id="compare-select"
          className="cobre-select"
          value={compareId ?? ""}
          onChange={(e) => onCompare(e.target.value || null)}
        >
          <option value="">-- Nenhuma --</option>
          {batches
            .filter((b) => b.batch_id !== selectedId)
            .map((b) => (
              <option key={b.batch_id} value={b.batch_id}>
                {label(b, baselineId)}
              </option>
            ))}
        </select>
      </div>

      <button
        type="button"
        onClick={handleReload}
        className="cobre-reload"
        disabled={spinning}
      >
        <span className={spinning ? "cobre-spin" : undefined} aria-hidden>
          ↻
        </span>
        Atualizar
      </button>
    </div>
  );
}
