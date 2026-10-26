import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { makeBatch } from "@/shared/fixtures.testutil";
import * as results from "@/services/resultsApi";
import * as launcher from "@/services/launcherApi";
import { useHistory } from "./useHistory";

vi.mock("@/services/resultsApi");
vi.mock("@/services/launcherApi");

const b1 = makeBatch("b1", [["q1", "pass", "t"]], { timestamp: "2026-01-01T00:00:00", conjunto: "todos" });
const b2 = makeBatch("b2", [["q1", "pass", "t"]], { timestamp: "2026-01-02T00:00:00", conjunto: "todos" });

function mockData(file: { baselines: Record<string, string>; legacyId: string | null }) {
  vi.mocked(results.fetchIndex).mockResolvedValue({
    batches: [{ batch_id: "b1" }, { batch_id: "b2" }],
  } as never);
  vi.mocked(results.fetchBatch).mockImplementation(async (id) => (id === "b1" ? b1 : b2));
  vi.mocked(results.fetchBaselineFile).mockResolvedValue(file);
}

describe("useHistory", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("ordena da mais recente para a mais antiga", async () => {
    mockData({ baselines: { todos: "b1" }, legacyId: null });
    const { result } = renderHook(() => useHistory());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.batches.map((b) => b.batch_id)).toEqual(["b2", "b1"]);
    expect(result.current.baselines).toEqual({ todos: "b1" });
  });

  it("legacyId vira baseline do conjunto da bateria", async () => {
    mockData({ baselines: {}, legacyId: "b1" });
    const { result } = renderHook(() => useHistory());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.baselines).toEqual({ todos: "b1" });
  });

  it("baseline apontando para bateria fora do index e omitida sem erro", async () => {
    mockData({ baselines: {}, legacyId: "ausente" });
    const { result } = renderHook(() => useHistory());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.baselines).toEqual({});
    expect(result.current.error).toBeNull();
  });

  it("toggleBaseline define ou limpa e recarrega o arquivo", async () => {
    mockData({ baselines: {}, legacyId: null });
    vi.mocked(launcher.setBaseline).mockResolvedValue();
    vi.mocked(launcher.clearBaseline).mockResolvedValue();
    const { result } = renderHook(() => useHistory());
    await waitFor(() => expect(result.current.loading).toBe(false));

    vi.mocked(results.fetchBaselineFile).mockResolvedValue({ baselines: { todos: "b2" }, legacyId: null });
    await act(() => result.current.toggleBaseline(b2));
    expect(launcher.setBaseline).toHaveBeenCalledWith("todos", "b2");
    expect(result.current.baselines).toEqual({ todos: "b2" });

    vi.mocked(results.fetchBaselineFile).mockResolvedValue({ baselines: {}, legacyId: null });
    await act(() => result.current.toggleBaseline(b2));
    expect(launcher.clearBaseline).toHaveBeenCalledWith("todos");
    expect(result.current.baselines).toEqual({});
  });
});
