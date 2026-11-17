export interface CasoDaLista {
  id: string;
  query: string;
}

interface Props {
  cases: CasoDaLista[];
  selectedGroup: string | null;
  selectedCaseId: string | null;
  onSelectCase: (id: string) => void;
}

/** Lista de casos (coluna esquerda) para escolher o caso da carga. */
export function CaseList({ cases, selectedGroup, selectedCaseId, onSelectCase }: Props) {
  return (
    <aside className="nm-case-list" aria-label="Testes">
      <div className="nm-case-list-head nm-muted">
        {cases.length} teste(s)
        {selectedGroup ? ` · grupo: ${selectedGroup}` : ""}
      </div>
      <ul>
        {cases.map((c) => (
          <li key={c.id}>
            <button
              type="button"
              className="nm-case-item"
              data-selected={selectedCaseId === c.id}
              onClick={() => onSelectCase(c.id)}
            >
              <span className="nm-case-item-query">{c.query}</span>
              <span className="nm-case-item-id">{c.id}</span>
            </button>
          </li>
        ))}
      </ul>
    </aside>
  );
}
