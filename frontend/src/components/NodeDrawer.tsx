import type { VisEdge, VisMolNode, VisNode, VisRxnNode } from "../types";
import { MoleculeView } from "./MoleculeView";
import { Button } from "./ui/Button";

export type DrawerSelection =
  | { kind: "molecule"; mol: VisMolNode }
  | { kind: "reaction"; rxn: VisRxnNode }
  | { kind: "edge"; edge: VisEdge; nodes: VisNode[] }
  | null;

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="text-[11px] font-medium uppercase tracking-wide text-slate-400">{label}</p>
      <div className="mt-0.5 text-sm text-slate-700">{children}</div>
    </div>
  );
}

export function NodeDrawer({ selection, onClose }: { selection: DrawerSelection; onClose: () => void }) {
  if (!selection) return null;
  return (
    <div
      data-testid="node-drawer"
      className="absolute right-0 top-0 z-10 flex h-full w-96 flex-col gap-3 overflow-y-auto border-l border-slate-200 bg-white p-4 shadow-xl"
    >
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-800">
          {selection.kind === "molecule" ? "分子节点" : selection.kind === "reaction" ? "反应节点" : "边信息"}
        </h3>
        <button
          data-testid="drawer-close"
          aria-label="关闭"
          onClick={onClose}
          className="rounded px-2 py-0.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
        >
          ✕
        </button>
      </div>

      {selection.kind === "molecule" && (
        <div className="space-y-3">
          <MoleculeView smiles={selection.mol.smiles} width={320} height={220} />
          <Field label="SMILES">
            <div className="flex items-start gap-2">
              <code className="min-w-0 flex-1 break-all font-mono text-xs" data-testid="drawer-smiles">
                {selection.mol.smiles}
              </code>
              <Button
                size="sm"
                onClick={() => navigator.clipboard?.writeText(selection.mol.smiles).catch(() => {})}
              >
                复制
              </Button>
            </div>
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="role">{selection.mol.role}</Field>
            <Field label="cs_score">
              {selection.mol.cs_score != null ? selection.mol.cs_score.toFixed(2) : "—"}
            </Field>
            <Field label="classification">{selection.mol.classification ?? "—"}</Field>
            <Field label="depth">{selection.mol.depth}</Field>
          </div>
        </div>
      )}

      {selection.kind === "reaction" && (
        <div className="space-y-3">
          <Field label="label">
            <p className="font-medium">{selection.rxn.label}</p>
          </Field>
          <Field label="depth">{selection.rxn.depth}</Field>
          <Field label="reaction_smiles">
            <code data-testid="drawer-rxn-smiles" className="block break-all font-mono text-xs text-slate-700">
              {selection.rxn.reaction_smiles ?? "—"}
            </code>
          </Field>
        </div>
      )}

      {selection.kind === "edge" && (
        <div className="space-y-3">
          <Field label="source">{selection.edge.source}</Field>
          <Field label="target">{selection.edge.target}</Field>
          <Field label="type">{selection.edge.type ?? "—"}</Field>
        </div>
      )}
    </div>
  );
}
