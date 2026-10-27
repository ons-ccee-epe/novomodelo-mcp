import { useLoadLauncher } from "@/services/api/useLoadLauncher";
import { LoadDoneSummary, LoadFinished } from "./components/LoadFinished";
import { LoadLauncher } from "./components/LoadLauncher";
import { LoadProgress } from "./components/LoadProgress";

const NOOP = () => {};

/** Área "Carga": dispara e acompanha um teste de carga; as cargas gravadas ficam no Histórico. */
export function Load() {
  const launcher = useLoadLauncher(NOOP);
  const run = launcher.run;

  return (
    <div className="cobre-shell">
      <LoadLauncher launcher={launcher} />
      {run && (launcher.busy || run.status !== "pending") && (
        <LoadProgress
          run={run}
          stopping={launcher.stopping}
          onStop={launcher.stop}
          action={<LoadFinished run={run} />}
          summary={run.load_id ? <LoadDoneSummary loadId={run.load_id} /> : undefined}
        />
      )}
    </div>
  );
}
