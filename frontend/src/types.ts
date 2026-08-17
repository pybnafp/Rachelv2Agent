export type JobStatus = "queued" | "running" | "succeeded" | "partial" | "failed" | "cancelled";
export interface JobOut {
  id: string; smiles: string; name: string; status: JobStatus; error: string;
  stats: Record<string, any>; created_at: string; started_at: string | null; finished_at: string | null;
}
export interface VisMolNode { id: string; type: "molecule"; smiles: string; role: "target" | "intermediate" | "terminal"; depth: number; cs_score?: number; classification?: string; }
export interface VisRxnNode { id: string; type: "reaction"; label: string; depth: number; reaction_smiles?: string; }
export type VisNode = VisMolNode | VisRxnNode;
export interface VisEdge { source: string; target: string; type?: string; }
export interface Visualization { nodes: VisNode[]; edges: VisEdge[]; meta?: Record<string, any>; }
export interface ResultOut { job: JobOut; visualization?: Visualization; terminals?: any[]; metrics?: Record<string, number | boolean>; }
