import { Fragment, useMemo, useState } from "react";

import { statusIcon } from "@/shared/constants/status";
import { groupForCase } from "@/shared/toolGroups";
import type { BatchResult, TestResult } from "@/shared/types";
import { TestDetail } from "./table/TestDetail";
import { TestFilters, type FilterState } from "./table/TestFilters";

const QUERY_PREVIEW_CHARS = 60;
const EXPECTED_PREVIEW_TOOLS = 2;

interface Props {
  batch: BatchResult;
  /** Grupo selecionado externamente (cards de MetricsByGroup). */
  groupFilter: string | null;
}

function expectedDisplay(tr: TestResult): string {
  if (tr.expected_tool) return tr.expected_tool;
  const tools = tr.expected_tools ?? [];
  if (tools.length === 0) return "-";
  const head = tools.slice(0, EXPECTED_PREVIEW_TOOLS).join(" | ");
  const extra = tools.length - EXPECTED_PREVIEW_TOOLS;
  return extra > 0 ? `${head} (+${extra})` : head;
}

function shorten(text: string): string {
  return text.length > QUERY_PREVIEW_CHARS ? `${text.slice(0, QUERY_PREVIEW_CHARS)}…` : text;
}

function matches(tr: TestResult, f: FilterState, groupFilter: string | null): boolean {
  const search = f.queryText.toLowerCase().trim();
  if (f.status !== "all" && tr.status !== f.status) return false;
  if (search && !tr.query.toLowerCase().includes(search)) return false;
  if (f.selectedTags.size > 0 && !tr.tags.some((t) => f.selectedTags.has(t))) return false;
  return !groupFilter || groupForCase(tr) === groupFilter;
}

function toggled(set: Set<string>, value: string): Set<string> {
  const next = new Set(set);
  if (next.has(value)) next.delete(value);
  else next.add(value);
  return next;
}

function TestRow({ tr, open, onToggle }: { tr: TestResult; open: boolean; onToggle: () => void }) {
  const expected = expectedDisplay(tr);
  return (
    <Fragment>
      <tr className="cobre-row-clickable" onClick={onToggle} aria-expanded={open}>
        <td>
          <code>{tr.test_id}</code>
        </td>
        <td title={tr.query}>{shorten(tr.query)}</td>
        <td>{expected}</td>
        <td>{tr.actual_tool ?? "-"}</td>
        <td>
          <span className="cobre-status" data-status={tr.status}>
            {statusIcon(tr.status)} {tr.status}
          </span>
        </td>
        <td>{tr.latency_ms.toFixed(0)}ms</td>
      </tr>
      {open && (
        <tr>
          <td colSpan={6} className="cobre-row-detail">
            <TestDetail tr={tr} expected={expected} />
          </td>
        </tr>
      )}
    </Fragment>
  );
}

/** Tabela de resultados com filtros e detalhe expansível por teste. */
export function TestTable({ batch, groupFilter }: Props) {
  const results = useMemo(() => batch.test_results ?? [], [batch]);
  const [filters, setFilters] = useState<FilterState>({
    status: "all",
    queryText: "",
    selectedTags: new Set(),
  });
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const allTags = useMemo(() => [...new Set(results.flatMap((tr) => tr.tags))].sort(), [results]);
  const rows = useMemo(
    () => results.filter((tr) => matches(tr, filters, groupFilter)),
    [results, filters, groupFilter],
  );

  if (results.length === 0) {
    return (
      <section className="cobre-section">
        <h2 className="cobre-section-title">Resultados dos Testes</h2>
        <div className="cobre-no-data">Nenhum resultado de teste disponível</div>
      </section>
    );
  }

  return (
    <section className="cobre-section">
      <h2 className="cobre-section-title">Resultados dos Testes</h2>
      <TestFilters
        filters={filters}
        allTags={allTags}
        shown={rows.length}
        total={results.length}
        groupFilter={groupFilter}
        onStatus={(status) => setFilters((f) => ({ ...f, status }))}
        onQueryText={(queryText) => setFilters((f) => ({ ...f, queryText }))}
        onToggleTag={(tag) => setFilters((f) => ({ ...f, selectedTags: toggled(f.selectedTags, tag) }))}
      />
      <table className="cobre-table">
        <thead>
          <tr>
            <th>Test ID</th>
            <th>Query</th>
            <th>Expected Tool</th>
            <th>Actual Tool</th>
            <th>Status</th>
            <th>Latency</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((tr) => (
            <TestRow
              key={tr.test_id}
              tr={tr}
              open={expanded.has(tr.test_id)}
              onToggle={() => setExpanded((prev) => toggled(prev, tr.test_id))}
            />
          ))}
        </tbody>
      </table>
    </section>
  );
}
