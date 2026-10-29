import { Link } from "react-router-dom";

import { ROUTES } from "@/shared/constants/Routes";

/** Alterna a lista do Histórico entre as rodadas da bateria e as cargas. */
export function HistoryKindSwitch({ loads }: { loads: boolean }) {
  return (
    <nav className="nm-kind-switch" aria-label="Tipo de execução">
      <Link
        to={ROUTES.history.path}
        className="nm-kind-switch-link"
        aria-current={loads ? undefined : "page"}
      >
        Rodadas
      </Link>
      <Link
        to={ROUTES.historyLoad.path}
        className="nm-kind-switch-link"
        aria-current={loads ? "page" : undefined}
      >
        Carga
      </Link>
    </nav>
  );
}
