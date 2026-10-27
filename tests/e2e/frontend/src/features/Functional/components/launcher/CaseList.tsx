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
      <span className="cobre-status" data-status="running" aria-label="rodando">
        <span className="cobre-spin" aria-hidden>
          ↻
        </span>{" "}
        rodando
      </span>
    );
  }
  if (!result) return <span className="cobre-status">pronto</span>;
  return (
    <span className="cobre-status" data-status={result.status}>
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
    <aside className="cobre-case-list" aria-label="Testes">
      <div className="cobre-case-list-head cobre-muted">
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
                className="cobre-case-item"
                data-selected={selectedCaseId === c.id}
                data-status={result?.status ?? (running ? "running" : "")}
                onClick={() => onSelectCase(c.id)}
              >
                <span className="cobre-case-item-query">{c.query}</span>
                <span className="cobre-case-item-id">{c.id}</span>
                <span className="cobre-case-item-side">
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
