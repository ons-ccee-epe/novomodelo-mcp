import { useMemo, useState } from "react";

import { statusIcon } from "@/shared/constants/status";
import { groupForCase } from "@/shared/toolGroups";
import type { TestResult, TestStatus } from "@/shared/types";
import { TestDetail } from "./TestDetail";

export type Change = "broke" | "fixed";

const STATUSES: TestStatus[] = ["pass", "partial", "fail", "timeout", "skip"];
const MARKER: Record<Change, string> = {
  broke: "✗ passou a falhar",
  fixed: "✓ passou a passar",
};

interface Props {
  results: TestResult[];
  changes: Map<string, Change>;
  openId: string | null;
  onOpen: (id: string | null) => void;
}

function expectedDisplay(tr: TestResult): string {
  if (tr.expected_tool) return tr.expected_tool;
  return tr.expected_tools?.join(" | ") || "-";
}

export function QuestionList({ results, changes, openId, onOpen }: Props) {
  const [status, setStatus] = useState("all");
  const [group, setGroup] = useState("all");

  const groups = useMemo(() => [...new Set(results.map(groupForCase))].sort(), [results]);
  const visible = results.filter(
    (tr) =>
      tr.test_id === openId ||
      ((status === "all" || tr.status === status) &&
        (group === "all" || groupForCase(tr) === group)),
  );

  return (
    <section className="cobre-section" aria-label="Perguntas">
      <h3 className="cobre-section-title">Perguntas</h3>
      <div className="cobre-filters">
        <div className="cobre-field">
          <label htmlFor="question-status" className="cobre-field-label">
            Status
          </label>
          <select
            id="question-status"
            className="cobre-filter-select"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
          >
            <option value="all">Todos</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>
        <div className="cobre-field">
          <label htmlFor="question-group" className="cobre-field-label">
            Grupo
          </label>
          <select
            id="question-group"
            className="cobre-filter-select"
            value={group}
            onChange={(e) => setGroup(e.target.value)}
          >
            <option value="all">Todos</option>
            {groups.map((g) => (
              <option key={g} value={g}>
                {g}
              </option>
            ))}
          </select>
        </div>
        <span className="cobre-muted cobre-filter-count">
          Mostrando {visible.length} de {results.length}
        </span>
      </div>
      <ul className="cobre-question-list">
        {visible.map((tr) => {
          const open = tr.test_id === openId;
          const change = changes.get(tr.test_id);
          return (
            <li key={tr.test_id} className="cobre-question" data-question-id={tr.test_id}>
              <button
                type="button"
                className="cobre-question-row"
                aria-expanded={open}
                onClick={() => onOpen(open ? null : tr.test_id)}
              >
                <code>{tr.test_id}</code>
                <span className="cobre-status" data-status={tr.status}>
                  {statusIcon(tr.status)} {tr.status}
                </span>
                {change && (
                  <span className="cobre-change-marker" data-kind={change}>
                    {MARKER[change]}
                  </span>
                )}
                <span className="cobre-muted cobre-question-latency">
                  {Math.round(tr.latency_ms)} ms
                </span>
              </button>
              {open && <TestDetail tr={tr} expected={expectedDisplay(tr)} />}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
