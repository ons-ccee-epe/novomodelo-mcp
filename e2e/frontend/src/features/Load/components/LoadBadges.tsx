interface Props {
  /** Grava arquivos: roda numa cópia das fixtures por sessão. */
  writes?: boolean;
  /** Sobe o bridge ou a CLI do solver a cada chamada. */
  heavy?: boolean;
}

/** Selos de uma tool ou caso: "grava · cópia por sessão" e/ou "pesada". Sem nenhum, não renderiza nada. */
export function LoadBadges({ writes = false, heavy = false }: Props) {
  if (!writes && !heavy) return null;
  return (
    <>
      {writes && (
        <span
          className="nm-load-badge"
          data-kind="writes"
          title="Grava arquivos: cada sessão roda numa cópia das fixtures"
        >
          grava · cópia por sessão
        </span>
      )}
      {heavy && (
        <span
          className="nm-load-badge"
          data-kind="heavy"
          title="Pesada: sobe o bridge ou a CLI do solver a cada chamada"
        >
          pesada
        </span>
      )}
    </>
  );
}
