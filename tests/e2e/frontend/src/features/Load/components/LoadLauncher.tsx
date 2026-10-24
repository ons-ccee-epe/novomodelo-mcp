import type { LoadLauncherData } from "@/services/api/useLoadLauncher";
import { LoadForm } from "./LoadForm";
import { LoadProgress } from "./LoadProgress";

function LauncherOffline() {
  return (
    <div className="cobre-banner" data-kind="warning">
      <strong>Launcher de testes offline.</strong> Para disparar uma carga pela UI, suba o launcher
      de dev em outro terminal:
      <pre className="cobre-code">
        pip install -r tests/e2e/launcher/requirements.txt{"\n"}
        python -m tests.e2e.launcher.serve
      </pre>
      Sem ele, esta tela mostra as cargas já gravadas (somente leitura).
    </div>
  );
}

/** Formulário de disparo da carga, com o progresso ao vivo e o botão de parar. */
export function LoadLauncher({ launcher }: { launcher: LoadLauncherData }) {
  const { run, busy, error } = launcher;

  if (launcher.checking) {
    return (
      <div className="cobre-launcher cobre-muted" data-state="checking">
        Verificando o launcher de testes…
      </div>
    );
  }
  if (!launcher.available) return <LauncherOffline />;

  return (
    <section className="cobre-launcher" aria-label="Disparar carga">
      {launcher.limits ? (
        <LoadForm
          tools={launcher.tools}
          limits={launcher.limits}
          disabled={busy}
          onStart={launcher.start}
        />
      ) : (
        <div className="cobre-banner" data-kind="critical">
          O launcher não informou as tools e os limites do teste de carga.
        </div>
      )}
      {run && (busy || run.status !== "pending") && (
        <LoadProgress run={run} stopping={launcher.stopping} onStop={launcher.stop} />
      )}
      {error && (
        <div className="cobre-banner" data-kind="critical">
          {error}
        </div>
      )}
    </section>
  );
}
