import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const RAIZ = resolve(dirname(fileURLToPath(import.meta.url)), "../..");

describe("package.json", () => {
  const pacote = JSON.parse(readFileSync(resolve(RAIZ, "package.json"), "utf-8")) as {
    dependencies: Record<string, string>;
    devDependencies: Record<string, string>;
    engines: { node: string };
  };

  it("fixa cada dependência numa versão exata", () => {
    for (const [nome, versao] of Object.entries({ ...pacote.dependencies, ...pacote.devDependencies })) {
      expect(versao, nome).toMatch(/^\d+\.\d+\.\d+$/);
    }
  });

  it("fixa o Node numa versão exata", () => {
    expect(pacote.engines.node).toMatch(/^\d+\.\d+\.\d+$/);
  });
});
