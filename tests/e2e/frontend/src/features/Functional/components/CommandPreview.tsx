import { useEffect, useState } from "react";

import { fetchCommandPreview, type CommandPreview as Preview } from "@/services/launcherApi";
import type { LauncherScope } from "./TestLauncher";

const DEBOUNCE_MS = 300;

function CopyableCommand({ title, text }: { title: string; text: string }) {
  return (
    <div className="cobre-command">
      <div className="cobre-command-head">
        <strong>{title}</strong>
        <button
          type="button"
          className="cobre-btn cobre-btn-ghost"
          onClick={() => void navigator.clipboard?.writeText(text)}
        >
          Copiar
        </button>
      </div>
      <pre className="cobre-code">{text}</pre>
    </div>
  );
}

/** Comando equivalente ao disparo da tela, para repetir fora da UI. */
export function CommandPreview({
  provider,
  scope,
}: {
  provider: string | null;
  scope: LauncherScope;
}) {
  const [preview, setPreview] = useState<Preview | null>(null);
  const tagsKey = scope.tags?.join(",") ?? "";
  const caseId = scope.caseId;

  useEffect(() => {
    let alive = true;
    const timer = setTimeout(() => {
      fetchCommandPreview({
        provider,
        tags: tagsKey ? tagsKey.split(",") : undefined,
        caseId,
      })
        .then((p) => alive && setPreview(p))
        .catch(() => alive && setPreview(null));
    }, DEBOUNCE_MS);
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [provider, tagsKey, caseId]);

  if (!preview) return null;
  return (
    <section className="cobre-command-preview" aria-label="Comando equivalente">
      <h2>Comando equivalente</h2>
      {preview.terminal ? (
        <CopyableCommand title="Bateria pelo terminal" text={preview.terminal} />
      ) : (
        <p className="cobre-muted">{preview.terminal_note}</p>
      )}
      <CopyableCommand title="Comando do agente por pergunta" text={preview.agent} />
    </section>
  );
}
