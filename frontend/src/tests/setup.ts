import "@testing-library/jest-dom/vitest";

// React Flow (@xyflow/react) requires ResizeObserver, missing in jsdom.
class ResizeObserverPolyfill {
  observe() {}
  unobserve() {}
  disconnect() {}
}
if (typeof globalThis.ResizeObserver === "undefined") {
  (globalThis as any).ResizeObserver = ResizeObserverPolyfill;
}

// d3-zoom/d3-drag (used by React Flow) read `event.view.document`; events
// dispatched by user-event in jsdom carry a null view. Default it to window.
if (typeof window !== "undefined") {
  Object.defineProperty(window.MouseEvent.prototype, "view", {
    configurable: true,
    get(this: MouseEvent) {
      return (this as any)._jsdomView ?? window;
    },
  });
}
