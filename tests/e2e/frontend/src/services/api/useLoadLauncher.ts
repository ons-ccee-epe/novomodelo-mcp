import { useCallback, useEffect, useRef, useState } from "react";

import { isFinished, launcherHealthy } from "@/services/launcherApi";
import {
  cancelLoadRun,
  fetchLoadRunStates,
  fetchLoadTools,
  pollLoadRun,
  startLoadRun,
  type LoadLimits,
  type LoadRunState,
  type LoadToolInfo,
  type StartLoadBody,
} from "@/services/loadApi";

export interface LoadLauncherData {
  /** Launcher de dev no ar? (habilita o disparo) */
  available: boolean;
  checking: boolean;
  tools: LoadToolInfo[];
  limits: LoadLimits | null;
  /** Carga em andamento ou a última desta sessão, para o progresso ao vivo. */
  run: LoadRunState | null;
  busy: boolean;
  error: string | null;
  start: (body: StartLoadBody) => void;
  /** Para a carga (encerra os servidores; nada é gravado). */
  stop: () => void;
  /** Parada pedida e ainda não concluída. */
  stopping: boolean;
}

/**
 * Interação com o launcher de dev para o teste de carga: descobre as tools e os limites,
 * dispara, acompanha por polling e para. Ao reabrir a tela com uma carga em andamento,
 * retoma o acompanhamento. Ao terminar com sucesso, chama onFinished.
 */
export function useLoadLauncher(onFinished: () => void): LoadLauncherData {
  const [available, setAvailable] = useState(false);
  const [checking, setChecking] = useState(true);
  const [tools, setTools] = useState<LoadToolInfo[]>([]);
  const [limits, setLimits] = useState<LoadLimits | null>(null);
  const [run, setRun] = useState<LoadRunState | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stopRequested, setStopRequested] = useState(false);

  const onFinishedRef = useRef(onFinished);
  useEffect(() => {
    onFinishedRef.current = onFinished;
  }, [onFinished]);

  // Um controller por montagem: sair da tela cancela o polling (a carga segue no launcher).
  const abortRef = useRef<AbortController | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    abortRef.current = controller;
    return () => controller.abort();
  }, []);

  const follow = useCallback(
    (initial: LoadRunState) => {
      const signal = abortRef.current?.signal;
      setBusy(true);
      setRun(initial);
      pollLoadRun(initial.run_id, setRun, { signal })
        .then((final) => {
          setRun(final);
          if (final.status === "done") onFinishedRef.current();
          else if (final.status === "error") setError(final.error ?? "A carga falhou.");
        })
        .catch((e: unknown) => {
          if (signal?.aborted) return;
          setError(e instanceof Error ? e.message : String(e));
        })
        .finally(() => {
          if (!signal?.aborted) setBusy(false);
        });
    },
    [],
  );

  useEffect(() => {
    let alive = true;
    (async () => {
      setChecking(true);
      const ok = await launcherHealthy();
      if (!alive) return;
      setAvailable(ok);
      if (ok) {
        try {
          const [catalog, states] = await Promise.all([fetchLoadTools(), fetchLoadRunStates()]);
          if (!alive) return;
          setTools(catalog.tools);
          setLimits(catalog.limits);
          const active = states.find((s) => !isFinished(s.status));
          if (active) follow(active);
        } catch (e: unknown) {
          if (alive) setError(e instanceof Error ? e.message : String(e));
        }
      }
      if (alive) setChecking(false);
    })();
    return () => {
      alive = false;
    };
  }, [follow]);

  const start = useCallback(
    (body: StartLoadBody) => {
      setBusy(true);
      setError(null);
      setStopRequested(false);
      startLoadRun(body)
        .then(follow)
        .catch((e: unknown) => {
          setBusy(false);
          setError(e instanceof Error ? e.message : String(e));
        });
    },
    [follow],
  );

  const stop = useCallback(() => {
    if (!run || isFinished(run.status)) return;
    setStopRequested(true);
    cancelLoadRun(run.run_id)
      // O polling pode já ter recebido o estado final; a resposta do cancel não o sobrescreve.
      .then((next) => setRun((prev) => (prev && isFinished(prev.status) ? prev : next)))
      .catch((e: unknown) => {
        setStopRequested(false);
        setError(e instanceof Error ? e.message : String(e));
      });
  }, [run]);

  return {
    available,
    checking,
    tools,
    limits,
    run,
    busy,
    error,
    start,
    stop,
    stopping: busy && (stopRequested || Boolean(run?.cancel_requested)),
  };
}
