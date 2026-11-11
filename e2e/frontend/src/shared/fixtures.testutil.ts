import type { BatchResult, TestResult, TestStatus } from "./types";

export type Row = [id: string, status: TestStatus, expectedTool: string | null];

export function makeBatch(
  batchId: string,
  rows: Row[],
  extra: Partial<BatchResult> = {},
): BatchResult {
  const test_results = rows.map(
    ([test_id, status, expected_tool]) =>
      ({
        test_id,
        status,
        expected_tool,
        expected_tools: null,
      }) as TestResult,
  );
  return {
    batch_id: batchId,
    timestamp: "2026-01-01T00:00:00",
    test_results,
    ...extra,
  } as BatchResult;
}
