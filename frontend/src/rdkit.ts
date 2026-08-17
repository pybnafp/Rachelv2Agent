let ready: Promise<any> | null = null;

export function getRDKit(): Promise<any> {
  if (!ready) {
    ready = (window as any).initRDKitModule({
      locateFile: (f: string) => `/rdkit/${f}`,
    }) as Promise<any>;
  }
  return ready as Promise<any>;
}
