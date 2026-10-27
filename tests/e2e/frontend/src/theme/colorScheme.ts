import { useCallback, useState } from "react";

export type ColorScheme = "light" | "dark";

const STORAGE_KEY = "cobre-color-scheme";

function stored(): ColorScheme | null {
  try {
    const value = window.localStorage.getItem(STORAGE_KEY);
    return value === "light" || value === "dark" ? value : null;
  } catch {
    return null;
  }
}

function preferred(): ColorScheme {
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

/** data-theme liga os tokens de styles.css; a classe é a que o Radix Themes lê no modo "inherit". */
function apply(scheme: ColorScheme) {
  const root = document.documentElement;
  root.dataset.theme = scheme;
  root.classList.toggle("dark", scheme === "dark");
  root.classList.toggle("light", scheme === "light");
}

/** Chamado antes do primeiro render, para a página não piscar no tema errado. */
export function applyInitialColorScheme() {
  apply(stored() ?? preferred());
}

export function useColorScheme(): [ColorScheme, () => void] {
  const [scheme, setScheme] = useState<ColorScheme>(() => stored() ?? preferred());
  const toggle = useCallback(() => {
    setScheme((current) => {
      const next = current === "dark" ? "light" : "dark";
      apply(next);
      try {
        window.localStorage.setItem(STORAGE_KEY, next);
      } catch {
        // Sem storage, o tema vale só até recarregar.
      }
      return next;
    });
  }, []);
  return [scheme, toggle];
}
