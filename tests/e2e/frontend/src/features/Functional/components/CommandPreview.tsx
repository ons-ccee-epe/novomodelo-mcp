import { useEffect, useState } from "react";

import { fetchCommandPreview, type CommandPreview as Preview } from "@/services/launcherApi";
import type { LauncherScope } from "./TestLauncher";

const DEBOUNCE_MS = 300;

function CopyableCommand({ title, text }: { title: string; text: string }) {
  return (
    <div className="nm-command">
      <div className="nm-command-head">
        <strong>{title}</strong>
        <button
          type="button"
          className="nm-btn nm-btn-sm"
          onClick={() => void navigator.clipboard?.writeText(text)}
        >
          Copiar
        </button>
      </div>
      <pre className="nm-code">{text}</pre>
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
    <details className="nm-command-preview" aria-label="Comando equivalente">
      <summary>Comando equivalente</summary>
      <div className="nm-command-preview-body">
        {preview.terminal ? (
          <CopyableCommand title="Bateria pelo terminal" text={preview.terminal} />
        ) : (
          <p className="nm-muted">{preview.terminal_note}</p>
        )}
        <CopyableCommand title="Comando do agente por pergunta" text={preview.agent} />
      </div>
    </details>
  );
}
