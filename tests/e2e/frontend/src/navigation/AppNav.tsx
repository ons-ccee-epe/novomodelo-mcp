import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";

import { launcherHealthy } from "@/services/launcherApi";
import { fetchIndex } from "@/services/resultsApi";
import { ROUTES } from "@/shared/constants/Routes";
import { useColorScheme } from "@/theme/colorScheme";

const LINKS = [
  { to: ROUTES.functional.path, label: "Testes Funcionais" },
  { to: ROUTES.load.path, label: "Testes de Carga" },
  { to: ROUTES.history.path, label: "Histórico" },
] as const;

interface LatestBatch {
  id: string;
  version: string | null;
}

/** Bateria mais recente do index; null se o index falha ou não tem baterias. */
function useLatestBatch(): LatestBatch | null {
  const [latest, setLatest] = useState<LatestBatch | null>(null);
  useEffect(() => {
    let alive = true;
    fetchIndex()
      .then(({ batches }) => {
        const first = batches[0];
        if (!alive || !first) return;
        const version = first.version && first.version !== "unknown" ? first.version : null;
        setLatest({ id: first.batch_id, version });
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, []);
  return latest;
}

/** Publica a altura real do cabeçalho em --cobre-header-h (o painel lateral do histórico gruda abaixo dele). */
function useHeaderHeight(ref: React.RefObject<HTMLElement | null>) {
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const publish = () =>
      document.documentElement.style.setProperty("--cobre-header-h", `${el.offsetHeight}px`);
    publish();
    const observer = new ResizeObserver(publish);
    observer.observe(el);
    return () => observer.disconnect();
  }, [ref]);
}

function MoonIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
    </svg>
  );
}

function SunIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </svg>
  );
}

function GearIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" />
    </svg>
  );
}

/** Engrenagem: informações do ambiente (última bateria, versão, launcher, transporte). */
function SettingsMenu({ latest }: { latest: LatestBatch | null }) {
  const [open, setOpen] = useState(false);
  const [online, setOnline] = useState<boolean | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const { pathname } = useLocation();

  useEffect(() => setOpen(false), [pathname]);

  useEffect(() => {
    if (!open) return;
    let alive = true;
    launcherHealthy().then((ok) => alive && setOnline(ok));
    const onPointer = (e: PointerEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      alive = false;
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const launcherText = online === null ? "verificando…" : online ? "online" : "offline";

  return (
    <div className="cobre-settings" ref={rootRef}>
      <button
        type="button"
        className="cobre-icon-btn"
        aria-label="Informações do ambiente"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <GearIcon />
      </button>
      {open && (
        <dl className="cobre-settings-panel" aria-label="Ambiente">
          <div className="cobre-settings-row">
            <dt>Bateria</dt>
            <dd>{latest?.id ?? "—"}</dd>
          </div>
          <div className="cobre-settings-row">
            <dt>Versão do MCP</dt>
            <dd>{latest?.version ? `v${latest.version}` : "—"}</dd>
          </div>
          <div className="cobre-settings-row">
            <dt>Launcher</dt>
            <dd>{launcherText}</dd>
          </div>
          <div className="cobre-settings-row">
            <dt>Transporte</dt>
            <dd>stdio</dd>
          </div>
        </dl>
      )}
    </div>
  );
}

/** Cabeçalho fixo: título, abas, modo noturno e as informações do ambiente. */
export function AppNav() {
  const latest = useLatestBatch();
  const [scheme, toggleScheme] = useColorScheme();
  const headerRef = useRef<HTMLElement>(null);
  useHeaderHeight(headerRef);
  const dark = scheme === "dark";
  return (
    <header className="cobre-header" ref={headerRef}>
      <div className="cobre-header-inner">
        <h1 className="cobre-header-title">Testes Automatizados · MCP NovoModelo</h1>
        <nav className="cobre-nav" aria-label="Áreas do painel">
          {LINKS.map((link) => (
            <NavLink key={link.to} to={link.to} className="cobre-nav-link">
              {link.label}
            </NavLink>
          ))}
        </nav>
        <div className="cobre-header-actions">
          <button
            type="button"
            className="cobre-icon-btn"
            aria-label={dark ? "Usar modo claro" : "Usar modo noturno"}
            title={dark ? "Modo claro" : "Modo noturno"}
            onClick={toggleScheme}
          >
            {dark ? <SunIcon /> : <MoonIcon />}
          </button>
          <SettingsMenu latest={latest} />
        </div>
      </div>
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
