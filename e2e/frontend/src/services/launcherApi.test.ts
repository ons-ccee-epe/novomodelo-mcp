import { afterEach, describe, expect, it, vi } from "vitest";

import { isFinished, launcherHealthy, waitOrAbort } from "@/services/launcherApi";

afterEach(() => vi.unstubAllGlobals());

describe("launcherApi", () => {
  it("isFinished reconhece os estados finais", () => {
    expect(isFinished("done")).toBe(true);
    expect(isFinished("cancelled")).toBe(true);
    expect(isFinished("running")).toBe(false);
  });

  it("launcherHealthy é falso quando o launcher não responde", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    expect(await launcherHealthy()).toBe(false);
  });

  it("waitOrAbort rejeita quando o signal é abortado", async () => {
    const controller = new AbortController();
    const espera = waitOrAbort(10_000, controller.signal);
    controller.abort();
    await expect(espera).rejects.toBeDefined();
  });
});
