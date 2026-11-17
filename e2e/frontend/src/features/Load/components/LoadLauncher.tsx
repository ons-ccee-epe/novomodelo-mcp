import type { LoadLauncherData } from "@/services/api/useLoadLauncher";
import { LoadForm } from "./LoadForm";

function LauncherOffline() {
  return (
    <div className="nm-banner" data-kind="warning">
      <strong>Launcher de testes offline.</strong> Para disparar uma carga pela UI, suba o launcher
      de dev em outro terminal:
      <pre className="nm-code">
        uv sync --package novomodelo-mcp-e2e{"\n"}
        uv run --package novomodelo-mcp-e2e python -m novomodelo_mcp_e2e.launcher.serve
      </pre>
      As cargas já gravadas continuam no Histórico.
    </div>
  );
}

/** Formulário de disparo da carga. */
export function LoadLauncher({ launcher }: { launcher: LoadLauncherData }) {
  const { busy, error } = launcher;

  if (launcher.checking) {
    return (
      <div className="nm-launcher nm-muted" data-state="checking">
        Verificando o launcher de testes…
      </div>
    );
  }
  if (!launcher.available) return <LauncherOffline />;

  return (
    <section aria-label="Disparar carga">
      {launcher.limits ? (
        <LoadForm
          tools={launcher.tools}
          limits={launcher.limits}
          disabled={busy}
          onStart={launcher.start}
          agent={launcher.agent}
          agentError={launcher.agentError}
          capacity={launcher.capacity}
          capacityError={launcher.capacityError}
          onRequestCapacity={launcher.requestCapacity}
        />
      ) : (
        <div className="nm-banner" data-kind="critical">
          O launcher não informou as tools e os limites do teste de carga.
        </div>
      )}
      {error && (
        <div className="nm-banner" data-kind="critical">
          {error}
        </div>
      )}
    </section>
  );
}
