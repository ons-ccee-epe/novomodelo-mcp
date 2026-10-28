import { useCallback, useState } from "react";

import { useLauncher } from "@/services/api/useLauncher";
import { CommandPreview } from "./components/CommandPreview";
import { RunFinished } from "./components/RunFinished";
import { TestLauncher, type LauncherScope } from "./components/TestLauncher";
import { RunProgress } from "./components/launcher/RunProgress";

const NOOP = () => {};

/** Aba "Testes Funcionais": dispara os testes e acompanha a rodada ao vivo. */
export function Functional() {
  const launcher = useLauncher(NOOP);
  const [scope, setScope] = useState<LauncherScope>({});
  const onScopeChange = useCallback((s: LauncherScope) => setScope(s), []);
  const { run } = launcher;

  const online = launcher.available && !launcher.checking && !launcher.error;

  return (
    <div className="nm-shell">
      <TestLauncher
        launcher={launcher}
        onScopeChange={onScopeChange}
        progress={
          run &&
          (launcher.busy || run.status !== "pending") && (
            <RunProgress
              run={run}
              stopping={launcher.stopping}
              onStop={launcher.stop}
              action={<RunFinished run={run} />}
            />
          )
        }
        preview={
          online && (
            <CommandPreview
              provider={launcher.selectedProvider}
              scope={scope}
            />
          )
        }
      />
    </div>
  );
}
