import { NavLink, Outlet } from "react-router-dom";

import { ROUTES } from "@/shared/constants/Routes";

const LINKS = [
  { to: ROUTES.dashboard.path, label: "Dashboard", end: true },
  { to: ROUTES.load.path, label: "Carga", end: false },
] as const;

/** Barra de navegação entre as áreas do painel. */
export function AppNav() {
  return (
    <nav className="cobre-nav" aria-label="Áreas do painel">
      {LINKS.map((link) => (
        <NavLink
          key={link.to}
          to={link.to}
          end={link.end}
          className="cobre-nav-link"
        >
          {link.label}
        </NavLink>
      ))}
    </nav>
  );
}

/** Layout das rotas: a navegação acima e a tela da rota ativa abaixo. */
export function AppLayout() {
  return (
    <>
      <AppNav />
      <Outlet />
    </>
  );
}
