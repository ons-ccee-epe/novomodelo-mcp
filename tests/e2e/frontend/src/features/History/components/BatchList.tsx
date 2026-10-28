import { useMemo, useState } from "react";

import { pickReference } from "@/shared/comparison";
import { conjuntoLabel, conjuntoOf, conjuntoTitle } from "@/shared/conjunto";
import type { BatchResult } from "@/shared/types";
import { BatchCard } from "./BatchCard";

interface Props {
  batches: BatchResult[];
  baselines: Record<string, string>;
  selectedId: string | null;
  collapsed: boolean;
  onToggleCollapsed: () => void;
}

const OPTION_MAX_CHARS = 60;

interface Option {
  value: string;
  label: string;
  count: number;
}

function shorten(text: string): string {
  return text.length > OPTION_MAX_CHARS ? `${text.slice(0, OPTION_MAX_CHARS - 1)}…` : text;
}

/** Opções do filtro: a esteira, os grupos pelo nome e as avulsas pelo texto da pergunta. */
function conjuntoOptions(batches: BatchResult[]) {
  const byConjunto = new Map<string, Option>();
  for (const b of batches) {
    const value = conjuntoOf(b);
    const current = byConjunto.get(value);
    if (current) current.count += 1;
    else {
      const label = value.startsWith("grupo:")
        ? conjuntoLabel(value).replace(/^Grupo /, "")
        : shorten(conjuntoTitle(b));
      byConjunto.set(value, { value, label, count: 1 });
    }
  }
  const all = [...byConjunto.values()].sort((a, b) => a.label.localeCompare(b.label));
  return {
    todos: byConjunto.get("todos")?.count ?? 0,
    groups: all.filter((o) => o.value.startsWith("grupo:")),
    single: all.filter((o) => o.value.startsWith("pergunta:")),
  };
}

export function BatchList({ batches, baselines, selectedId, collapsed, onToggleCollapsed }: Props) {
  const [filter, setFilter] = useState("");

  const options = useMemo(() => conjuntoOptions(batches), [batches]);
  const visible = filter ? batches.filter((b) => conjuntoOf(b) === filter) : batches;

  const collapseButton = (
    <button
      type="button"
      className="nm-collapse-btn"
      aria-label={collapsed ? "Mostrar a lista de baterias" : "Recolher a lista de baterias"}
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
        <h2>Execuções</h2>
        <select
          className="nm-select"
          aria-label="Filtrar por conjunto"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        >
          <option value="">Todas ({batches.length})</option>
          {options.todos > 0 && <option value="todos">Esteira completa ({options.todos})</option>}
          {options.groups.length > 0 && (
            <optgroup label="Grupos">
              {options.groups.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label} ({o.count})
                </option>
              ))}
            </optgroup>
          )}
          {options.single.length > 0 && (
            <optgroup label="Perguntas avulsas">
              {options.single.map((o) => (
                <option key={o.value} value={o.value} title={o.value.slice("pergunta:".length)}>
                  {o.label} ({o.count})
                </option>
              ))}
            </optgroup>
          )}
        </select>
        <span className="nm-muted">
          {visible.length}/{batches.length}
        </span>
        {collapseButton}
      </div>
      <ul className="nm-batch-items">
        {visible.map((b) => (
          <BatchCard
            key={b.batch_id}
            batch={b}
            reference={pickReference(b, batches, baselines)}
            selected={b.batch_id === selectedId}
            isBaseline={baselines[conjuntoOf(b)] === b.batch_id}
          />
        ))}
      </ul>
    </div>
  );
}
