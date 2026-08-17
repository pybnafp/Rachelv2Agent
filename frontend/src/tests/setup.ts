import "@testing-library/jest-dom/vitest";

// jsdom 没有 EventSource：默认提供一个被动空实现，避免渲染含 SSE 组件的用例崩溃；
// 需要可控行为的测试用 vi.stubGlobal("EventSource", FakeEventSource) 覆盖。
class EventSourcePolyfill {
  url: string;
  closed = false;
  onerror: (() => void) | null = null;
  constructor(url: string) {
    this.url = url;
  }
  addEventListener() {}
  close() {
    this.closed = true;
  }
}
if (typeof globalThis.EventSource === "undefined") {
  (globalThis as any).EventSource = EventSourcePolyfill;
}

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
