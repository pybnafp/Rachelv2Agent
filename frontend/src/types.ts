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
export interface ResultOut {
  job: JobOut;
  visualization?: Visualization;
  terminals?: any[];
  metrics?: Record<string, number | boolean>;
  terminal_audit?: TerminalAudit | null;
}

export interface TraceStep {
  seq: number;
  command: string;
  args: Record<string, any>;
  result_summary: string;
  status: "ok" | "error";
  tokens: number;
  duration_ms: number;
  created_at: string;
}

export interface TerminalAuditResult {
  node_id: string;
  smiles: string;
  cs_score?: number | null;
  rachel_classification?: string;
  pubchem?: { queried?: boolean; best_cid?: number | null; best_cid_url?: string };
  pubchem_metrics?: { pubchem_cid_closed?: boolean; vendor_closed?: boolean };
  allowlist?: { hit?: boolean };
  buyability_decision?: Record<string, any>;
}

export interface TerminalAudit {
  available: boolean;
  error?: string;
  offline?: boolean;
  summary?: {
    total_terminals?: number;
    pubchem_cid_closed?: number;
    vendor_closed?: number;
    [key: string]: any;
  };
  results?: TerminalAuditResult[];
}
