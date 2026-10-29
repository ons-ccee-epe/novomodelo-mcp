import { useState } from "react";

import { indexEntryMode, type LoadIndexEntry, type LoadRunMode } from "@/shared/types";
import { LoadCard } from "./LoadCard";

const RELOAD_FEEDBACK_MS = 700;

interface Props {
  runs: LoadIndexEntry[];
  selectedId: string | null;
  collapsed: boolean;
  onToggleCollapsed: () => void;
  onReload: () => void;
}

/** Lista lateral das cargas gravadas, filtrável pelo modo. */
export function LoadList({ runs, selectedId, collapsed, onToggleCollapsed, onReload }: Props) {
  const [mode, setMode] = useState<LoadRunMode | "">("");
  const [spinning, setSpinning] = useState(false);

  const count = (m: LoadRunMode) => runs.filter((r) => indexEntryMode(r) === m).length;
  const visible = mode ? runs.filter((r) => indexEntryMode(r) === mode) : runs;

  function handleReload() {
    setSpinning(true);
    onReload();
    window.setTimeout(() => setSpinning(false), RELOAD_FEEDBACK_MS);
  }

  const collapseButton = (
    <button
      type="button"
      className="nm-collapse-btn"
      aria-label={collapsed ? "Mostrar a lista de cargas" : "Recolher a lista de cargas"}
      aria-expanded={!collapsed}
      onClick={onToggleCollapsed}
    >
      {collapsed ? "›" : "‹"}
    </button>
  );

  if (collapsed) {
    return <div className="nm-batch-list-head">{collapseButton}</div>;
  }

  return (
    <div className="nm-batch-list">
      <div className="nm-batch-list-head">
        <h2>Cargas</h2>
        <select
          className="nm-select"
          aria-label="Filtrar por modo"
          value={mode}
          onChange={(e) => setMode(e.target.value as LoadRunMode | "")}
        >
          <option value="">Todas ({runs.length})</option>
          <option value="tools">Tools ({count("tools")})</option>
          <option value="agent">Agente ({count("agent")})</option>
        </select>
        <button
          type="button"
          className="nm-collapse-btn"
          aria-label="Atualizar a lista de cargas"
          title="Atualizar"
          onClick={handleReload}
          disabled={spinning}
        >
          <span className={spinning ? "nm-spin" : undefined} aria-hidden>
            ↻
          </span>
        </button>
        {collapseButton}
      </div>
      <ul className="nm-batch-items" aria-label="Cargas gravadas">
        {visible.map((r) => (
          <LoadCard key={r.load_id} entry={r} selected={r.load_id === selectedId} />
        ))}
      </ul>
    </div>
  );
}
