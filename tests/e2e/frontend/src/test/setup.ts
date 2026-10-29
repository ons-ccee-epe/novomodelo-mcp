import "@testing-library/jest-dom/vitest";

// O jsdom não tem ResizeObserver, que o ResponsiveContainer do Recharts exige ao montar.
class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}

globalThis.ResizeObserver ??= ResizeObserverStub as unknown as typeof ResizeObserver;
