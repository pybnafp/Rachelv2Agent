/** 可编程的 EventSource 替身（jsdom 无原生实现） */
export class FakeEventSource {
  static instances: FakeEventSource[] = [];
  /** 置 true 后，之后创建的实例在构造后立即触发 onerror（模拟连接失败） */
  static autoErrorNext = false;
  url: string;
  closed = false;
  handlers: Record<string, (ev: { data: string }) => void> = {};
  onerror: (() => void) | null = null;

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
    if (FakeEventSource.autoErrorNext) {
      // 构造后异步触发 onerror，模拟连接失败降级
      Promise.resolve().then(() => this.onerror?.());
    }
  }

  addEventListener(name: string, fn: (ev: { data: string }) => void) {
    this.handlers[name] = fn;
  }

  close() {
    this.closed = true;
  }

  trigger(name: string, payload: unknown) {
    this.handlers[name]?.({ data: JSON.stringify(payload) });
  }

  error() {
    this.onerror?.();
  }

  static reset() {
    FakeEventSource.instances = [];
    FakeEventSource.autoErrorNext = false;
  }
}

export const resetEventSources = () => FakeEventSource.reset();
export const instances = () => FakeEventSource.instances;
