import { Fragment } from "react";
import { ArrowRight } from "lucide-react";
import { MoleculeView } from "./MoleculeView";

/** 工单 T2：反应 SMILES 渲染成「反应物 → 产物」图式；解析失败兜底为原始文本。 */
function Side({ smiles, width, height }: { smiles: string; width: number; height: number }) {
  const mols = smiles.split(".").filter(Boolean);
  return (
    <div className="flex flex-wrap items-center justify-center gap-1">
      {mols.map((m, i) => (
        <Fragment key={i}>
          {i > 0 && <span className="text-sm text-slate-400" aria-label="与">＋</span>}
          <MoleculeView smiles={m} width={width} height={height} />
        </Fragment>
      ))}
    </div>
  );
}

export function ReactionView({
  reactionSmiles,
  width = 110,
  height = 78,
}: {
  reactionSmiles?: string;
  width?: number;
  height?: number;
}) {
  if (!reactionSmiles) return <p className="text-sm text-slate-500">—</p>;
  const parts = reactionSmiles.split(">>");
  if (parts.length !== 2 || !parts[0].trim() || !parts[1].trim()) {
    // 兜底：不是 "A>>B" 形式时展示原始文本（不白屏，工单验收要求）
    return (
      <code className="block break-all rounded-lg bg-surface-2 p-2 font-mono text-xs text-slate-700">
        {reactionSmiles}
      </code>
    );
  }
  return (
    <div
      data-testid="reaction-view"
      className="flex flex-wrap items-center justify-center gap-2 rounded-lg bg-surface-2 p-2"
    >
      <Side smiles={parts[0]} width={width} height={height} />
      <ArrowRight size={20} className="shrink-0 text-sky-600" aria-label="生成" />
      <Side smiles={parts[1]} width={width} height={height} />
    </div>
  );
}
