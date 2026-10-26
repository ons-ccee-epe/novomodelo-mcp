import { useEffect, useMemo, useState, type ReactNode } from "react";

import type { CaseMeta, RunResultItem } from "@/services/launcherApi";
import type { LauncherData } from "@/services/api/useLauncher";
import { groupForCase } from "@/shared/toolGroups";
import { CaseDetail, type CaseSummary } from "./launcher/CaseDetail";
import { CaseList } from "./launcher/CaseList";
import { GroupFilter } from "./launcher/GroupFilter";
import { LauncherControls } from "./launcher/LauncherControls";

export interface LauncherScope {
  tags?: string[];
  caseId?: string;
}

function groupCases(cases: CaseMeta[]): Array<[string, string[]]> {
  const map = new Map<string, string[]>();
  for (const c of cases) {
    const g = groupForCase(c);
    map.set(g, [...(map.get(g) ?? []), c.id]);
  }
  return [...map.entries()].sort((a, b) => a[0].localeCompare(b[0]));
}

function toSummary(c: CaseMeta): CaseSummary {
  return {
    id: c.id,
    query: c.query,
    expected: c.expected_tool ?? c.expected_tools?.join(" | ") ?? "—",
    tags: c.tags,
    timeoutS: c.timeout_s ?? null,
  };
}

function LauncherOffline() {
  return (
    <div className="cobre-banner" data-kind="warning">
      <strong>Launcher de testes offline.</strong> Para disparar testes pela UI,
      suba o launcher de dev em outro terminal:
      <pre className="cobre-code">
        pip install -r tests/e2e/launcher/requirements.txt{"\n"}
        python -m tests.e2e.launcher.serve
      </pre>
      As baterias já gravadas continuam na aba Histórico.
    </div>
  );
}

/**
 * Painel de disparo dos testes das tools MCP num provedor de IA: esteira
 * completa, por grupo ou um caso, com o progresso e o resultado ao vivo.
 */
export function TestLauncher({
  launcher,
  onScopeChange,
  preview,
}: {
  launcher: LauncherData;
  onScopeChange?: (scope: LauncherScope) => void;
  /** Renderizado logo abaixo do seletor de grupo. */
  preview?: ReactNode;
}) {
  const { cases, run, busy, error } = launcher;
  const [selectedGroup, setSelectedGroup] = useState<string | null>(null);
  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null);

  const groups = useMemo(() => groupCases(cases), [cases]);
  const visibleCases = useMemo(
    () =>
      selectedGroup
        ? cases.filter((c) => groupForCase(c) === selectedGroup)
        : cases,
    [cases, selectedGroup],
  );
  const resultById = useMemo(
    () =>
      new Map<string, RunResultItem>(
        (run?.results ?? []).map((r) => [r.test_id, r]),
      ),
    [run],
  );
  const selectedCase =
    visibleCases.find((c) => c.id === selectedCaseId) ?? null;
  const selectedCaseKey = selectedCase?.id ?? null;

  useEffect(() => {
    if (!onScopeChange) return;
    if (selectedCaseKey) onScopeChange({ caseId: selectedCaseKey });
    else if (selectedGroup) onScopeChange({ tags: [selectedGroup] });
    else onScopeChange({});
  }, [selectedGroup, selectedCaseKey, onScopeChange]);

  if (launcher.checking) {
    return (
      <div className="cobre-launcher cobre-muted" data-state="checking">
        Verificando o launcher de testes…
      </div>
    );
  }
  if (!launcher.available) return <LauncherOffline />;

  const noProvider = !launcher.providers.some((p) => p.installed);
  const canRun = !busy && !noProvider;
  const runningCaseId = busy ? (run?.current ?? null) : null;

  return (
    <section className="cobre-launcher" aria-label="Disparar testes">
      <LauncherControls
        providers={launcher.providers}
        selectedProvider={launcher.selectedProvider}
        onSelectProvider={launcher.setSelectedProvider}
        totalCases={cases.length}
        disabled={busy}
        noProvider={noProvider}
        onRunAll={launcher.runAll}
      />
      {noProvider && (
        <div className="cobre-banner" data-kind="critical">
          Nenhum provedor de IA instalado (kiro-cli ou claude não estão no
          PATH).
        </div>
      )}
      <GroupFilter
        groups={groups}
        totalCases={cases.length}
        selectedGroup={selectedGroup}
        visibleCount={visibleCases.length}
        busy={busy}
        canRun={canRun}
        onSelectGroup={setSelectedGroup}
        onRunGroup={(g) => launcher.runTags([g])}
      />
      {preview}
      {error && (
        <div className="cobre-banner" data-kind="critical">
          {error}
        </div>
      )}

      <div className="cobre-launcher-split">
        <CaseList
          cases={visibleCases}
          selectedGroup={selectedGroup}
          selectedCaseId={selectedCaseId}
          runningCaseId={runningCaseId}
          resultById={resultById}
          onSelectCase={setSelectedCaseId}
        />
        <div className="cobre-case-detail" aria-label="Detalhe do teste">
          {selectedCase ? (
            <CaseDetail
              caseMeta={toSummary(selectedCase)}
              result={resultById.get(selectedCase.id) ?? null}
              running={runningCaseId === selectedCase.id}
              canRun={canRun}
              onRun={() => launcher.runCase(selectedCase.id)}
            />
          ) : (
            <div className="cobre-no-data">
              Selecione um teste à esquerda para ver os detalhes e o resultado.
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
