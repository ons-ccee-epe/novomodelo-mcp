import { useEffect, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";

import { fetchIndex } from "@/services/resultsApi";
import { ROUTES } from "@/shared/constants/Routes";

const LINKS = [
  { to: ROUTES.functional.path, label: "Testes Funcionais" },
  { to: ROUTES.load.path, label: "Testes de Carga" },
  { to: ROUTES.history.path, label: "Histórico" },
] as const;

/** Rótulo da bateria mais recente; vazio se o index falha ou não tem baterias. */
function useLatestBatchLabel(): string | null {
  const [label, setLabel] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    fetchIndex()
      .then(({ batches }) => {
        const latest = batches[0];
        if (!alive || !latest) return;
        const version =
          latest.version && latest.version !== "unknown" ? ` · v${latest.version}` : "";
        setLabel(`Bateria ${latest.batch_id}${version}`);
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, []);
  return label;
}

/** Cabeçalho fixo: título, última bateria e as abas das áreas do painel. */
export function AppNav() {
  const latest = useLatestBatchLabel();
  return (
    <header className="cobre-header">
      <div className="cobre-header-top">
        <h1 className="cobre-header-title">Testes Automatizados · MCP NovoModelo</h1>
        {latest && <span className="cobre-header-batch">{latest}</span>}
      </div>
      <nav className="cobre-nav" aria-label="Áreas do painel">
        {LINKS.map((link) => (
          <NavLink key={link.to} to={link.to} className="cobre-nav-link">
            {link.label}
          </NavLink>
        ))}
      </nav>
    </header>
  );
}

/** Layout das rotas: o cabeçalho acima e a tela da rota ativa abaixo. */
export function AppLayout() {
  return (
    <>
      <AppNav />
      <Outlet />
    </>
  );
}
