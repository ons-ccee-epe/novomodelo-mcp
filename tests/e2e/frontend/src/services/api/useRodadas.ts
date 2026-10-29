import { useCallback, useEffect, useState } from "react";

import {
  carregarRodada,
  carregarRodadas,
  type ResumoRodada,
  type Rodada,
} from "@/data/rodada";

function mensagem(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

export interface RodadasData {
  rodadas: ResumoRodada[];
  loading: boolean;
  error: string | null;
  reload: () => void;
}

/** As rodadas gravadas, da mais recente para a mais antiga. */
export function useRodadas(): RodadasData {
  const [rodadas, setRodadas] = useState<ResumoRodada[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const reload = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    carregarRodadas()
      .then((lista) => {
        if (!alive) return;
        setRodadas(lista);
        setError(null);
      })
      .catch((e: unknown) => alive && setError(mensagem(e)))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [tick]);

  return { rodadas, loading, error, reload };
}

export interface RodadaData {
  rodada: Rodada | null;
  loading: boolean;
  error: string | null;
}

/** Uma rodada completa; `null` em `id` não carrega nada. */
export function useRodada(id: string | null): RodadaData {
  const [estado, setEstado] = useState<RodadaData & { id: string | null }>({
    id: null,
    rodada: null,
    loading: false,
    error: null,
  });

  useEffect(() => {
    if (id === null) return;
    let alive = true;
    carregarRodada(id)
      .then((rodada) => alive && setEstado({ id, rodada, loading: false, error: null }))
      .catch((e: unknown) => alive && setEstado({ id, rodada: null, loading: false, error: mensagem(e) }));
    return () => {
      alive = false;
    };
  }, [id]);

  if (id === null) return { rodada: null, loading: false, error: null };
  if (estado.id !== id) return { rodada: null, loading: true, error: null };
  return { rodada: estado.rodada, loading: estado.loading, error: estado.error };
}

export interface RodadasCompletas {
  rodadas: Rodada[];
  loading: boolean;
  /** Quantas das pedidas não puderam ser lidas. */
  falhas: number;
}

/** Carrega várias rodadas de uma vez, para a evolução e a variação entre rodadas. */
export function useRodadasCompletas(ids: string[]): RodadasCompletas {
  const chave = ids.join("\n");
  const [estado, setEstado] = useState<RodadasCompletas & { chave: string }>({
    chave: "",
    rodadas: [],
    loading: false,
    falhas: 0,
  });

  useEffect(() => {
    if (chave === "") return;
    let alive = true;
    Promise.allSettled(chave.split("\n").map((id) => carregarRodada(id))).then((resultados) => {
      if (!alive) return;
      const rodadas = resultados.flatMap((r) => (r.status === "fulfilled" ? [r.value] : []));
      setEstado({ chave, rodadas, loading: false, falhas: resultados.length - rodadas.length });
    });
    return () => {
      alive = false;
    };
  }, [chave]);

  if (chave === "") return { rodadas: [], loading: false, falhas: 0 };
  if (estado.chave !== chave) return { rodadas: [], loading: true, falhas: 0 };
  return estado;
}
