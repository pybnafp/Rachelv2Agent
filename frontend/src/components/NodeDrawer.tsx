import { X } from "lucide-react";
import type { VisEdge, VisMolNode, VisNode, VisRxnNode } from "../types";
import { CONFIDENCE_ZH, CS_SCORE_HINT, classificationZh } from "../lib/labels";
import { MoleculeView } from "./MoleculeView";
import { ReactionView } from "./ReactionView";
import { Badge } from "./ui/Badge";
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

/** 工单 T12：反应节点抽屉的「为什么这么设计」区块（字段缺省时整块隐藏）。 */
function DesignRationale({ rxn }: { rxn: VisRxnNode }) {
  const d = rxn.llm_decision;
  if (!d || (!d.selection_reasoning && !d.risk_assessment && !d.rejected_alternatives?.length)) return null;
  return (
    <div data-testid="drawer-rationale" className="rounded-lg border border-slate-200 bg-surface-2 p-3">
      <p className="mb-2 text-xs font-semibold text-slate-700">为什么这么设计</p>
      <div className="space-y-2">
        {d.confidence && (
          <p className="flex items-center gap-2 text-xs text-slate-600">
            置信度
            <Badge color={d.confidence === "high" ? "emerald" : d.confidence === "low" ? "red" : "amber"}>
              {CONFIDENCE_ZH[d.confidence] ?? d.confidence}
            </Badge>
          </p>
        )}
        {d.selection_reasoning && (
          <p className="text-xs leading-relaxed text-slate-600">{d.selection_reasoning}</p>
        )}
        {d.risk_assessment && (
          <p className="text-xs leading-relaxed text-amber-700">风险：{d.risk_assessment}</p>
        )}
        {!!d.rejected_alternatives?.length && (
          <details>
            <summary className="cursor-pointer text-xs text-sky-600">
              其他考虑过的方案（{d.rejected_alternatives.length}）
            </summary>
            <ul className="mt-1 space-y-1">
              {d.rejected_alternatives!.map((r, i) => (
                <li key={i} className="text-xs text-slate-500">
                  <span className="font-mono">{r.action_id ?? r.id ?? `#${i + 1}`}</span>
                  {r.reason ? `：${r.reason}` : ""}
                </li>
              ))}
            </ul>
          </details>
        )}
      </div>
    </div>
  );
}

export function NodeDrawer({ selection, onClose }: { selection: DrawerSelection; onClose: () => void }) {
  if (!selection) return null;
  const mol = selection.kind === "molecule" ? selection.mol : null;
  const rxn = selection.kind === "reaction" ? selection.rxn : null;
  const listed = !!rxn?.template_evidence;
  return (
    <div
      data-testid="node-drawer"
      className="absolute right-0 top-0 z-10 flex h-full w-96 flex-col gap-3 overflow-y-auto border-l border-slate-200 bg-surface p-4 shadow-xl"
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
          <X size={14} aria-hidden />
        </button>
      </div>

      {mol && (
        <div className="space-y-3">
          <MoleculeView smiles={mol.smiles} width={320} height={220} />
          <Field label="SMILES">
            <div className="flex items-start gap-2">
              <code className="min-w-0 flex-1 break-all font-mono text-xs" data-testid="drawer-smiles">
                {mol.smiles}
              </code>
              <Button
                size="sm"
                onClick={() => navigator.clipboard?.writeText(mol.smiles).catch(() => {})}
              >
                复制
              </Button>
            </div>
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="role">{mol.role}</Field>
            <Field label="cs_score">
              <span title={CS_SCORE_HINT} className="cursor-help border-b border-dotted border-slate-400">
                {mol.cs_score != null ? mol.cs_score.toFixed(2) : "—"}
              </span>
            </Field>
            <Field label="classification">
              {classificationZh(mol.classification) ?? "—"}
              {mol.classification && classificationZh(mol.classification) !== mol.classification && (
                <span className="ml-1 font-mono text-[10px] text-slate-400">{mol.classification}</span>
              )}
            </Field>
            <Field label="depth">{mol.depth}</Field>
          </div>
        </div>
      )}

      {rxn && (
        <div className="space-y-3">
          <Field label="label">
            <p className="font-medium">{rxn.label}</p>
          </Field>
          <Field label="依据">
            {listed ? (
              <span className="inline-flex items-center gap-1 text-xs text-sky-600">
                模板依据（listed）
                {rxn.template_evidence?.template_name && (
                  <span className="font-mono text-[10px] text-slate-400">{rxn.template_evidence.template_name}</span>
                )}
              </span>
            ) : (
              <span className="text-xs text-violet-600">本次现推的假设（custom）</span>
            )}
          </Field>
          <Field label="depth">{rxn.depth}</Field>
          {/* 工单 T2：反应式渲染成图，原始文本保留在下方供复制 */}
          <Field label="reaction_smiles">
            <div className="space-y-2">
              <ReactionView reactionSmiles={rxn.reaction_smiles} />
              <code data-testid="drawer-rxn-smiles" className="block break-all font-mono text-xs text-slate-700">
                {rxn.reaction_smiles ?? "—"}
              </code>
            </div>
          </Field>
          {/* 工单 T10：试剂小结构图（旧任务无字段时隐藏） */}
          {!!rxn.reagents?.length && (
            <Field label={`reagents（${rxn.reagents.length}）`}>
              <div className="flex flex-wrap gap-1" data-testid="drawer-reagents">
                {rxn.reagents.map((r, i) => (
                  <MoleculeView key={i} smiles={r} width={90} height={64} />
                ))}
              </div>
            </Field>
          )}
          <DesignRationale rxn={rxn} />
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
