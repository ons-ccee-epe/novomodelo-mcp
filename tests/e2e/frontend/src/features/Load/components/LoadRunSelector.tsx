import { useState } from "react";

import type { LoadIndexEntry } from "@/shared/types";
import { fmtLoadId, fmtMs, fmtPercent, fmtRate } from "../format";

const RELOAD_FEEDBACK_MS = 700;

interface Props {
  runs: LoadIndexEntry[];
  selectedId: string | null;
  compareId: string | null;
  onSelect: (id: string) => void;
  /** ``null`` = sem comparação; ``undefined`` = voltar ao padrão (a carga anterior). */
  onCompare: (id: string | null | undefined) => void;
  onReload: () => void;
}

function label(r: LoadIndexEntry): string {
  const s = r.summary;
  const partial = r.interrupted ? " (parcial)" : "";
  return `${fmtLoadId(r.load_id)} | ${r.config.concurrency} cli × ${r.config.duration_seconds}s | ${fmtRate(
    s.throughput_cps,
  )} · err ${fmtPercent(s.error_rate)} · p95 ${fmtMs(s.p95_ms)}${partial}`;
}

/** Seleção da carga exibida e da carga de comparação, e recarga do índice. */
export function LoadRunSelector({
  runs,
  selectedId,
  compareId,
  onSelect,
  onCompare,
  onReload,
}: Props) {
  const [spinning, setSpinning] = useState(false);

  function handleReload() {
    setSpinning(true);
    onReload();
    window.setTimeout(() => setSpinning(false), RELOAD_FEEDBACK_MS);
  }

  return (
    <div className="cobre-topbar">
      <div className="cobre-field">
        <label htmlFor="load-select" className="cobre-field-label">
          Carga exibida
        </label>
        <select
          id="load-select"
          className="cobre-select"
          value={selectedId ?? ""}
          onChange={(e) => onSelect(e.target.value)}
        >
          {runs.map((r, i) => (
            <option key={r.load_id} value={r.load_id}>
              {label(r)}
              {i === 0 ? " (mais recente)" : ""}
            </option>
          ))}
        </select>
      </div>

      <div className="cobre-field">
        <label htmlFor="load-compare-select" className="cobre-field-label">
          Comparar com
        </label>
        <select
          id="load-compare-select"
          className="cobre-select"
          value={compareId ?? ""}
          onChange={(e) => onCompare(e.target.value || null)}
        >
          <option value="">-- Nenhuma --</option>
          {runs
            .filter((r) => r.load_id !== selectedId)
            .map((r) => (
              <option key={r.load_id} value={r.load_id}>
                {label(r)}
              </option>
            ))}
        </select>
      </div>

      <button type="button" onClick={() => onCompare(undefined)} className="cobre-reload">
        Comparar com a anterior
      </button>

      <button type="button" onClick={handleReload} className="cobre-reload" disabled={spinning}>
        <span className={spinning ? "cobre-spin" : undefined} aria-hidden>
          ↻
        </span>
        Atualizar
      </button>
    </div>
  );
}
