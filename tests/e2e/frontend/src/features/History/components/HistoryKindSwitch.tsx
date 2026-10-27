import { Link } from "react-router-dom";

import { ROUTES } from "@/shared/constants/Routes";

/** Alterna a lista do Histórico entre as baterias funcionais e as cargas. */
export function HistoryKindSwitch({ loads }: { loads: boolean }) {
  return (
    <nav className="cobre-kind-switch" aria-label="Tipo de execução">
      <Link
        to={ROUTES.history.path}
        className="cobre-kind-switch-link"
        aria-current={loads ? undefined : "page"}
      >
        Funcionais
      </Link>
      <Link
        to={ROUTES.historyLoad.path}
        className="cobre-kind-switch-link"
        aria-current={loads ? "page" : undefined}
      >
        Carga
      </Link>
    </nav>
  );
}
