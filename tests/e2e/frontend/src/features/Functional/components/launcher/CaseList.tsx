import type { CaseMeta, RunResultItem } from "@/services/launcherApi";
import { STATUS_LABEL, statusIcon } from "@/shared/constants/status";

interface Props {
  cases: CaseMeta[];
  selectedGroup: string | null;
  selectedCaseId: string | null;
  runningCaseId: string | null;
  resultById: Map<string, RunResultItem>;
  onSelectCase: (id: string) => void;
}

function CaseBadge({ running, result }: { running: boolean; result?: RunResultItem }) {
  if (running) {
    return (
      <span className="nm-status" data-status="running" aria-label="rodando">
        <span className="nm-spin" aria-hidden>
          ↻
        </span>{" "}
        rodando
      </span>
    );
  }
  if (!result) return <span className="nm-status">pronto</span>;
  return (
    <span className="nm-status" data-status={result.status}>
      {statusIcon(result.status)} {STATUS_LABEL[result.status] ?? result.status}
    </span>
  );
}

/** Lista de casos (coluna esquerda), com o status ao vivo de cada um. */
export function CaseList({
  cases,
  selectedGroup,
  selectedCaseId,
  runningCaseId,
  resultById,
  onSelectCase,
}: Props) {
  return (
    <aside className="nm-case-list" aria-label="Testes">
      <div className="nm-case-list-head nm-muted">
        {cases.length} teste(s)
        {selectedGroup ? ` · grupo: ${selectedGroup}` : ""}
      </div>
      <ul>
        {cases.map((c) => {
          const result = resultById.get(c.id);
          const running = runningCaseId === c.id;
          return (
            <li key={c.id}>
              <button
                type="button"
                className="nm-case-item"
                data-selected={selectedCaseId === c.id}
                data-status={result?.status ?? (running ? "running" : "")}
                onClick={() => onSelectCase(c.id)}
              >
                <span className="nm-case-item-query">{c.query}</span>
                <span className="nm-case-item-id">{c.id}</span>
                <span className="nm-case-item-side">
                  <CaseBadge running={running} result={result} />
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </aside>
  );
}
