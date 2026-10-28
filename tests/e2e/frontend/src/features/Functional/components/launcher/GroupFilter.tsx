interface Props {
  groups: Array<[string, string[]]>;
  totalCases: number;
  selectedGroup: string | null;
  visibleCount: number;
  busy: boolean;
  canRun: boolean;
  onSelectGroup: (group: string | null) => void;
  onRunGroup: (group: string) => void;
}

/** Filtro por grupo de tool; com um grupo escolhido, habilita executar só ele. */
export function GroupFilter({
  groups,
  totalCases,
  selectedGroup,
  visibleCount,
  busy,
  canRun,
  onSelectGroup,
  onRunGroup,
}: Props) {
  return (
    <div className="nm-launcher-groups">
      <span className="nm-field-label">Grupo</span>
      <button
        type="button"
        className="nm-btn nm-btn-ghost"
        data-active={selectedGroup === null}
        onClick={() => onSelectGroup(null)}
        disabled={busy}
      >
        todos ({totalCases})
      </button>
      {groups.map(([g, ids]) => (
        <button
          key={g}
          type="button"
          className="nm-btn nm-btn-ghost"
          data-active={selectedGroup === g}
          onClick={() => onSelectGroup(g)}
          disabled={busy}
          title={`Filtra os ${ids.length} caso(s) do grupo ${g}`}
        >
          {g} ({ids.length})
        </button>
      ))}

      {selectedGroup && (
        <button
          type="button"
          className="nm-btn nm-btn-primary nm-btn-run-group"
          onClick={() => onRunGroup(selectedGroup)}
          disabled={!canRun}
          title={`Executa os ${visibleCount} caso(s) do grupo ${selectedGroup}`}
        >
          ▶ Executar grupo selecionado ({visibleCount})
        </button>
      )}
    </div>
  );
}
