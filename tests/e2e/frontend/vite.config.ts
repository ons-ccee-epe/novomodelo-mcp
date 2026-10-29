import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

const here = dirname(fileURLToPath(import.meta.url));

// Defaults espelhados em .env.template; o dev server sobe sem .env.
const DEFAULT_DEV_HOST = "127.0.0.1";
const DEFAULT_DEV_PORT = "5174";
const DEFAULT_LAUNCHER_URL = "http://127.0.0.1:5175";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, here, "VITE_");
  return {
    // base relativa: a SPA e servida como asset estatico (hospedagem estática).
    base: "./",
    plugins: [react()],
    resolve: {
      alias: { "@": resolve(here, "src") },
    },
    server: {
      host: env.VITE_DEV_HOST || DEFAULT_DEV_HOST,
      port: Number(env.VITE_DEV_PORT || DEFAULT_DEV_PORT),
      // O painel só lê do launcher de dev (FastAPI): as rodadas em /api e as cargas em /data.
      proxy: Object.fromEntries(
        ["/api", "/data"].map((rota) => [
          rota,
          { target: env.VITE_LAUNCHER_URL || DEFAULT_LAUNCHER_URL, changeOrigin: true },
        ]),
      ),
    },
    test: {
      globals: true,
      environment: "jsdom",
      setupFiles: ["./src/test/setup.ts"],
    },
  };
});
