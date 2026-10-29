import { useCallback, useEffect, useRef, useState } from "react";

import {
  isFinished,
  launcherHealthy,
  PROVEDORES_DA_CARGA,
  type ProviderId,
} from "@/services/launcherApi";
import {
  cancelLoadRun,
  fetchLoadCapacity,
  fetchLoadCases,
  fetchLoadRunStates,
  fetchLoadTools,
  pollLoadRun,
  startLoadRun,
  type AgentCatalog,
  type CapacityQuery,
  type LoadCapacity,
  type LoadLimits,
  type LoadMode,
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
  /** Casos, limites e provedores do modo agente; null se não carregaram (ver agentError). */
  agent: AgentCatalog | null;
  /** Falha ao carregar casos/provedores: o modo tools segue disponível. */
  agentError: string | null;
  /** Capacidade da máquina para o modo/provedor pedido por último. */
  capacity: LoadCapacity | null;
  capacityError: string | null;
  /**
   * Pede a capacidade de novo (a memória livre é um instantâneo); só o agente usa o provedor.
   * ``selection`` é o que vai rodar (tools marcadas ou caso/grupo): muda o custo por sessão.
   */
  requestCapacity: (
    mode: LoadMode,
    provider: ProviderId | null,
    selection?: CapacityQuery,
  ) => void;
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
 * Interação com o launcher de dev para o teste de carga: lista as tools, os casos, os
 * provedores e os limites, dispara, acompanha por polling e para. Ao reabrir a tela com uma carga em andamento,
 * retoma o acompanhamento. Ao terminar com sucesso, chama onFinished.
 */
export function useLoadLauncher(onFinished: () => void): LoadLauncherData {
  const [available, setAvailable] = useState(false);
  const [checking, setChecking] = useState(true);
  const [tools, setTools] = useState<LoadToolInfo[]>([]);
  const [limits, setLimits] = useState<LoadLimits | null>(null);
  const [agent, setAgent] = useState<AgentCatalog | null>(null);
  const [agentError, setAgentError] = useState<string | null>(null);
  const [capacity, setCapacity] = useState<LoadCapacity | null>(null);
  const [capacityError, setCapacityError] = useState<string | null>(null);
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

  // Só a resposta do último pedido vale: trocar de modo/provedor/seleção rápido não mistura capacidades.
  const capacityRequest = useRef(0);
  const requestCapacity = useCallback(
    (mode: LoadMode, provider: ProviderId | null, selection?: CapacityQuery) => {
      const id = ++capacityRequest.current;
      const signal = abortRef.current?.signal;
      setCapacity(null);
      setCapacityError(null);
      fetchLoadCapacity(mode, provider, selection)
        .then((next) => {
          if (id === capacityRequest.current && !signal?.aborted) setCapacity(next);
        })
        .catch((e: unknown) => {
          if (id === capacityRequest.current && !signal?.aborted) {
            setCapacityError(e instanceof Error ? e.message : String(e));
          }
        });
    },
    [],
  );

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
        try {
          const cases = await fetchLoadCases();
          if (!alive) return;
          setAgent({
            cases: cases.cases ?? [],
            limits: cases.limits,
            providers: PROVEDORES_DA_CARGA,
            defaultProvider: PROVEDORES_DA_CARGA[0]?.id ?? null,
          });
        } catch (reason: unknown) {
          if (alive) setAgentError(reason instanceof Error ? reason.message : String(reason));
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
    agent,
    agentError,
    capacity,
    capacityError,
    requestCapacity,
    run,
    busy,
    error,
    start,
    stop,
    stopping: busy && (stopRequested || Boolean(run?.cancel_requested)),
  };
}
