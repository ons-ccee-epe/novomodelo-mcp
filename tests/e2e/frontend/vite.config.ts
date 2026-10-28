import type { ServerResponse } from "node:http";
import { readFile, readdir } from "node:fs/promises";
import { dirname, extname, isAbsolute, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv, type Plugin } from "vite";

const here = dirname(fileURLToPath(import.meta.url));

// Defaults espelhados em .env.template; o dev server sobe sem .env.
const DEFAULT_DEV_HOST = "127.0.0.1";
const DEFAULT_DEV_PORT = "5174";
const DEFAULT_LAUNCHER_URL = "http://127.0.0.1:5175";

// Raizes dos resultados dos testes (fonte de verdade — NAO duplicamos dado).
// O frontend consome estes JSON em vez de gerar HTML.
const RESULTS_DIR = resolve(here, "..", "results");
const METRICS_DIR = resolve(here, "..", "metrics");

const LOCAL_HOST = /^(127\.0\.0\.1|localhost)(:\d+)?$/;

const MIME: Record<string, string> = {
  ".json": "application/json; charset=utf-8",
  ".jsonl": "application/x-ndjson; charset=utf-8",
};

/**
 * Serve os resultados dos testes sob /data/* diretamente do disco em dev.
 *
 * /data/results/<arquivo>   -> tests/e2e/results/<arquivo>
 * /data/metrics/<arquivo>   -> tests/e2e/metrics/<arquivo>
 * /data/results/            -> listagem dos *.json de results (indice derivado)
 *
 * Nenhum arquivo e copiado: cada request le o estado atual do disco, entao
 * rodar os testes e dar refresh ja mostra o resultado novo.
 */
function resultsDataPlugin(): Plugin {
  const roots: Record<string, string> = {
    results: RESULTS_DIR,
    metrics: METRICS_DIR,
  };

  async function send(res: ServerResponse, status: number, body: string, type: string) {
    res.statusCode = status;
    res.setHeader("Content-Type", type);
    res.setHeader("Cache-Control", "no-store");
    res.end(body);
  }

  return {
    name: "nm-results-data",
    configureServer(server) {
      server.middlewares.use(async (req, res, next) => {
        const url = req.url ? req.url.split("?")[0] : "";
        if (!url.startsWith("/data/")) return next();

        // Este hook roda antes do host check do Vite: sem isto, /data fica
        // legível por DNS rebinding.
        if (!LOCAL_HOST.test(req.headers.host ?? "")) {
          return send(res, 403, JSON.stringify({ error: "host nao permitido" }), MIME[".json"]);
        }

        let rest: string;
        try {
          rest = decodeURIComponent(url.slice("/data/".length));
        } catch {
          // URIError numa promise rejeitada derrubaria o dev server inteiro.
          return send(res, 400, JSON.stringify({ error: "url invalida" }), MIME[".json"]);
        }
        const [bucket, ...tail] = rest.split("/");
        const root = roots[bucket];
        if (!root) {
          return send(res, 404, JSON.stringify({ error: "bucket desconhecido" }), MIME[".json"]);
        }

        const name = tail.join("/");

        // Listagem derivada: GET /data/results/ -> { files: [...] }
        if (name === "" || name === undefined) {
          try {
            const entries = await readdir(root);
            const files = entries.filter((f) => f.endsWith(".json") || f.endsWith(".jsonl"));
            return send(res, 200, JSON.stringify({ files }), MIME[".json"]);
          } catch {
            return send(res, 200, JSON.stringify({ files: [] }), MIME[".json"]);
          }
        }

        // relative, nao startsWith: um irmao "results2" passaria num prefixo de string.
        const target = resolve(join(root, name));
        const rel = relative(resolve(root), target);
        if (rel.startsWith("..") || isAbsolute(rel)) {
          return send(res, 403, JSON.stringify({ error: "fora da raiz" }), MIME[".json"]);
        }

        try {
          const buf = await readFile(target, "utf-8");
          const type = MIME[extname(target)] ?? "application/octet-stream";
          return send(res, 200, buf, type);
        } catch {
          return send(res, 404, JSON.stringify({ error: "nao encontrado", name }), MIME[".json"]);
        }
      });
    },
  };
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, here, "VITE_");
  return {
    // base relativa: a SPA e servida como asset estatico (hospedagem estática).
    base: "./",
    plugins: [react(), resultsDataPlugin()],
    resolve: {
      alias: { "@": resolve(here, "src") },
    },
    server: {
      host: env.VITE_DEV_HOST || DEFAULT_DEV_HOST,
      port: Number(env.VITE_DEV_PORT || DEFAULT_DEV_PORT),
      // /api vai para o launcher de dev (FastAPI); /data continua pelo plugin acima.
      proxy: {
        "/api": {
          target: env.VITE_LAUNCHER_URL || DEFAULT_LAUNCHER_URL,
          changeOrigin: true,
        },
      },
    },
    test: {
      globals: true,
      environment: "jsdom",
      setupFiles: ["./src/test/setup.ts"],
    },
  };
});
