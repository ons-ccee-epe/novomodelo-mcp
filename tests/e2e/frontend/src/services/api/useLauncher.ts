import { useCallback, useEffect, useRef, useState } from "react";

import {
  cancelRun,
  fetchCases,
  fetchProviders,
  isFinished,
  launcherHealthy,
  pollRun,
  startRun,
  type CaseMeta,
  type ProviderId,
  type ProviderInfo,
  type RunState,
  type StartRunBody,
} from "@/services/launcherApi";

export interface LauncherData {
  /** Launcher de dev no ar? (habilita os disparos) */
  available: boolean;
  checking: boolean;
  providers: ProviderInfo[];
  /** Provedor escolhido no seletor (null = auto). */
  selectedProvider: ProviderId | null;
  setSelectedProvider: (p: ProviderId | null) => void;
  cases: CaseMeta[];
  /** Run em andamento/ultimo run, para a UI mostrar progresso. */
  run: RunState | null;
  busy: boolean;
  error: string | null;
  /** Dispara: esteira completa (sem args), por tags, ou um caso. */
  runAll: () => void;
  runTags: (tags: string[]) => void;
  runCase: (caseId: string) => void;
  /** Para o run em andamento (interrompe o caso atual; nenhuma bateria é gravada). */
  stop: () => void;
  /** Parada pedida e ainda não concluída. */
  stopping: boolean;
}

/**
 * Gerencia a interacao com o launcher de dev: detecta provedores e casos,
 * dispara runs e faz polling ate terminar. Ao terminar, chama onFinished
 * (o Dashboard usa isso para recarregar a bateria recem-gravada).
 */
export function useLauncher(onFinished: () => void): LauncherData {
  const [available, setAvailable] = useState(false);
  const [checking, setChecking] = useState(true);
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [selectedProvider, setSelectedProvider] = useState<ProviderId | null>(null);
  const [cases, setCases] = useState<CaseMeta[]>([]);
  const [run, setRun] = useState<RunState | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stopRequested, setStopRequested] = useState(false);

  // Descoberta inicial: launcher no ar? provedores? casos?
  useEffect(() => {
    let alive = true;
    (async () => {
      setChecking(true);
      const ok = await launcherHealthy();
      if (!alive) return;
      setAvailable(ok);
      if (ok) {
        try {
          const [prov, cs] = await Promise.all([fetchProviders(), fetchCases()]);
          if (!alive) return;
          setProviders(prov.providers);
          setSelectedProvider(prov.default);
          setCases(cs);
        } catch (e: unknown) {
          if (alive) setError(e instanceof Error ? e.message : String(e));
        }
      }
      if (alive) setChecking(false);
    })();
    return () => {
      alive = false;
    };
  }, []);

  // Um controller por montagem: o unmount cancela o polling em andamento.
  const abortRef = useRef<AbortController | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    abortRef.current = controller;
    return () => controller.abort();
  }, []);

  const dispatch = useCallback(
    (body: StartRunBody) => {
      const signal = abortRef.current?.signal;
      setBusy(true);
      setError(null);
      setStopRequested(false);
      startRun({ ...body, provider: selectedProvider })
        .then((state) => pollRun(state.run_id, setRun, { signal }))
        .then((final) => {
          setRun(final);
          if (final.status === "done") onFinished();
          else if (final.status === "error") setError(final.error ?? "Run falhou.");
        })
        .catch((e: unknown) => {
          if (signal?.aborted) return;
          setError(e instanceof Error ? e.message : String(e));
        })
        .finally(() => {
          if (!signal?.aborted) setBusy(false);
        });
    },
    [selectedProvider, onFinished],
  );

  const stop = useCallback(() => {
    if (!run || isFinished(run.status)) return;
    setStopRequested(true);
    cancelRun(run.run_id)
      // O polling pode já ter recebido o estado final; a resposta do cancel não o sobrescreve.
      .then((next) => setRun((prev) => (prev && isFinished(prev.status) ? prev : next)))
      .catch((e: unknown) => {
        setStopRequested(false);
        setError(e instanceof Error ? e.message : String(e));
      });
  }, [run]);

  const runAll = useCallback(() => dispatch({}), [dispatch]);
  const runTags = useCallback((tags: string[]) => dispatch({ tags }), [dispatch]);
  const runCase = useCallback((caseId: string) => dispatch({ case_id: caseId }), [dispatch]);

  return {
    available,
    checking,
    providers,
    selectedProvider,
    setSelectedProvider,
    cases,
    run,
    busy,
    error,
    runAll,
    runTags,
    runCase,
    stop,
    stopping: busy && (stopRequested || Boolean(run?.cancel_requested)),
  };
}
