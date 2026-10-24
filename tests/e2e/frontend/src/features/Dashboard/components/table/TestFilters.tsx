const STATUS_OPTIONS = [
  { value: "all", label: "All" },
  { value: "pass", label: "Pass" },
  { value: "partial", label: "Partial" },
  { value: "fail", label: "Fail" },
  { value: "timeout", label: "Timeout" },
  { value: "skip", label: "Skip" },
];

export interface FilterState {
  status: string;
  queryText: string;
  selectedTags: Set<string>;
}

interface Props {
  filters: FilterState;
  allTags: string[];
  shown: number;
  total: number;
  groupFilter: string | null;
  onStatus: (status: string) => void;
  onQueryText: (text: string) => void;
  onToggleTag: (tag: string) => void;
}

function TagFilter({ allTags, selected, onToggle }: {
  allTags: string[];
  selected: Set<string>;
  onToggle: (tag: string) => void;
}) {
  return (
    <div className="cobre-field">
      <span className="cobre-field-label">Tags</span>
      <div className="cobre-tag-filter">
        {allTags.map((tag) => (
          <label key={tag} className="cobre-tag-option" data-active={selected.has(tag)}>
            <input type="checkbox" checked={selected.has(tag)} onChange={() => onToggle(tag)} />
            {tag}
          </label>
        ))}
      </div>
    </div>
  );
}

/** Filtros da tabela de testes: status, busca na query e tags. */
export function TestFilters({
  filters,
  allTags,
  shown,
  total,
  groupFilter,
  onStatus,
  onQueryText,
  onToggleTag,
}: Props) {
  return (
    <div className="cobre-filters">
      <div className="cobre-field">
        <label htmlFor="test-status-filter" className="cobre-field-label">
          Status
        </label>
        <select
          id="test-status-filter"
          className="cobre-filter-select"
          value={filters.status}
          onChange={(e) => onStatus(e.target.value)}
        >
          {STATUS_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </div>

      <div className="cobre-field">
        <label htmlFor="test-query-filter" className="cobre-field-label">
          Buscar Query
        </label>
        <input
          id="test-query-filter"
          className="cobre-input"
          type="text"
          placeholder="Digite para buscar..."
          value={filters.queryText}
          onChange={(e) => onQueryText(e.target.value)}
        />
      </div>

      {allTags.length > 0 && (
        <TagFilter allTags={allTags} selected={filters.selectedTags} onToggle={onToggleTag} />
      )}

      <span className="cobre-muted cobre-filter-count">
        Mostrando {shown} de {total} testes
        {groupFilter ? ` · grupo: ${groupFilter}` : ""}
      </span>
    </div>
  );
}
