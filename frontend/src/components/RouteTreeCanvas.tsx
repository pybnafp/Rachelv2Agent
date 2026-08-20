import { useEffect, useMemo, useState } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  ControlButton,
  Handle,
  MarkerType,
  Position,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import { Lock, LockOpen, ShieldCheck, Sparkles } from "lucide-react";
import "@xyflow/react/dist/style.css";
import type { VisEdge, VisMolNode, VisRxnNode, Visualization } from "../types";
import { CS_SCORE_HINT, classificationZh } from "../lib/labels";
import { treeLayout } from "../lib/treeLayout";
import { MoleculeView } from "./MoleculeView";
import { NodeDrawer, type DrawerSelection } from "./NodeDrawer";

const ROLE_STYLE: Record<VisMolNode["role"], string> = {
  target: "border-blue-600 bg-blue-50",
  intermediate: "border-slate-400 bg-surface",
  terminal: "border-emerald-600 bg-emerald-50",
};

const ROLE_BADGE: Record<VisMolNode["role"], string> = {
  target: "bg-blue-600 text-white",
  intermediate: "bg-slate-200 text-slate-700",
  terminal: "bg-emerald-600 text-white",
};

/** 边的附着点（深度向下递增：上方收边 target、下方发边 source）。缺 Handle 时 React Flow 不会渲染任何边。 */
const HANDLE_CLS = "!h-1.5 !w-1.5 !border-0 !bg-slate-400 !opacity-70";

function MoleculeCard({ data }: { data: VisMolNode }) {
  const clsZh = classificationZh(data.classification);
  return (
    <div
      data-testid={`mol-card-${data.id}`}
      className={`w-44 overflow-visible rounded-xl border-2 shadow-sm ${ROLE_STYLE[data.role] ?? ROLE_STYLE.intermediate}`}
    >
      <Handle type="target" position={Position.Top} isConnectable={false} className={HANDLE_CLS} />
      <div className="flex items-center justify-center rounded-t-[10px] bg-surface p-1">
        <MoleculeView smiles={data.smiles} width={160} height={110} />
      </div>
      <div className="flex items-center justify-between gap-1 px-2 py-1">
        <span
          className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${ROLE_BADGE[data.role] ?? ROLE_BADGE.intermediate}`}
        >
          {data.role}
        </span>
        {/* 工单 T6/T9：CS 分值带说明 tooltip；classification 中文短标签上卡片 */}
        <span className="flex items-center gap-1 text-[10px] font-mono text-slate-600">
          {clsZh && (
            <span className="rounded bg-slate-100 px-1 py-0.5" title={`classification: ${data.classification}`}>
              {clsZh}
            </span>
          )}
          <span title={CS_SCORE_HINT} data-testid={`cs-score-${data.id}`}>
            {data.cs_score != null ? data.cs_score.toFixed(2) : "—"}
          </span>
        </span>
      </div>
      <Handle type="source" position={Position.Bottom} isConnectable={false} className={HANDLE_CLS} />
    </div>
  );
}

/** 工单 T3：反应节点从药丸升级成卡片（完整反应名不截断）；T10/T11：试剂小图 + listed/custom 标记。 */
function ReactionCard({ data }: { data: VisRxnNode }) {
  const listed = !!data.template_evidence;
  return (
    <div
      data-testid={`rxn-pill-${data.id}`}
      title={data.label}
      className="w-44 cursor-pointer rounded-xl border border-amber-400 bg-amber-50 p-2 text-center shadow-sm"
    >
      <Handle type="target" position={Position.Top} isConnectable={false} className={HANDLE_CLS} />
      <p className="break-words text-xs font-medium leading-snug text-amber-900">{data.label}</p>
      <div className="mt-1 flex items-center justify-center gap-2 text-[10px]">
        {listed ? (
          <span className="inline-flex items-center gap-0.5 text-sky-600" title="有已知反应模板依据（listed）">
            <ShieldCheck size={11} aria-hidden />
            模板
          </span>
        ) : (
          <span className="inline-flex items-center gap-0.5 text-violet-600" title="本次 LLM 现推的反应假设（custom）">
            <Sparkles size={11} aria-hidden />
            现推
          </span>
        )}
        {!!data.reagents?.length && (
          <span className="text-slate-500" title={(data.reagents ?? []).join(" · ")}>
            试剂×{data.reagents.length}
          </span>
        )}
      </div>
      {!!data.reagents?.length && (
        <div className="mt-1 flex flex-wrap items-center justify-center gap-1 border-t border-amber-200 pt-1">
          {(data.reagents ?? []).slice(0, 4).map((r, i) => (
            <MoleculeView key={i} smiles={r} width={56} height={40} />
          ))}
        </div>
      )}
      <Handle type="source" position={Position.Bottom} isConnectable={false} className={HANDLE_CLS} />
    </div>
  );
}

type MolFlowNode = Node<{ mol: VisMolNode }, "molecule">;
type RxnFlowNode = Node<{ rxn: VisRxnNode }, "reaction">;

export default function RouteTreeCanvas({ vis }: { vis: Visualization }) {
  const [drawer, setDrawer] = useState<DrawerSelection>(null);
  // 工单 T8：锁定 = 冻结画布平移缩放（不再切换节点可拖动状态）
  const [locked, setLocked] = useState(false);
  // close drawer when switching to a different visualization (job switch)
  useEffect(() => setDrawer(null), [vis]);

  const edgeById = useMemo(() => {
    const m = new Map<string, VisEdge>();
    vis.edges.forEach((e, i) => m.set(`e-${i}-${e.source}-${e.target}`, e));
    return m;
  }, [vis]);

  const { nodes, edges } = useMemo(() => {
    const positions = treeLayout(vis);
    const nodes: (MolFlowNode | RxnFlowNode)[] = vis.nodes.map((n) => {
      const p = positions.get(n.id) ?? { x: 0, y: 0 };
      const base = { id: n.id, position: p, draggable: false };
      return n.type === "molecule"
        ? ({
            ...base,
            type: "molecule" as const,
            data: { mol: n },
          } satisfies MolFlowNode)
        : ({
            ...base,
            type: "reaction" as const,
            data: { rxn: n },
          } satisfies RxnFlowNode);
    });
    const edges: Edge[] = vis.edges.map((e: VisEdge, i) => ({
      id: `e-${i}-${e.source}-${e.target}`,
      source: e.source,
      target: e.target,
      type: "smoothstep",
      animated: false,
      // 工单 T1：箭头画在较浅（更接近目标）一端，方向不再背离目标
      markerStart: { type: MarkerType.ArrowClosed },
    }));
    return { nodes, edges };
  }, [vis]);

  const onNodeClick = (_: unknown, node: Node) => {
    const raw = byIdLookup(vis, node.id);
    if (!raw) return;
    setDrawer(raw.type === "reaction" ? { kind: "reaction", rxn: raw } : { kind: "molecule", mol: raw });
  };

  const nodeTypes = useMemo(
    () => ({
      molecule: (props: NodeProps<MolFlowNode>) => <MoleculeCard data={props.data.mol} />,
      reaction: (props: NodeProps<RxnFlowNode>) => <ReactionCard data={props.data.rxn} />,
    }),
    []
  );

  return (
    <div className="relative h-[600px] w-full overflow-hidden rounded-xl border border-slate-200" data-testid="route-tree-canvas">
      {/* 工单 T5：常驻图例 */}
      <div
        data-testid="canvas-legend"
        className="pointer-events-none absolute left-2 top-2 z-[5] flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-slate-200 bg-surface px-3 py-1.5 text-[11px] text-slate-600 shadow-sm"
      >
        <span className="inline-flex items-center gap-1">
          <i className="inline-block h-2.5 w-2.5 rounded-sm border-2 border-blue-600 bg-blue-50" aria-hidden />
          目标
        </span>
        <span className="inline-flex items-center gap-1">
          <i className="inline-block h-2.5 w-2.5 rounded-sm border-2 border-slate-400 bg-surface" aria-hidden />
          中间体
        </span>
        <span className="inline-flex items-center gap-1">
          <i className="inline-block h-2.5 w-2.5 rounded-sm border-2 border-emerald-600 bg-emerald-50" aria-hidden />
          可购买原料
        </span>
        <span className="inline-flex items-center gap-0.5 text-sky-600">
          <ShieldCheck size={11} aria-hidden />
          模板
        </span>
        <span className="inline-flex items-center gap-0.5 text-violet-600">
          <Sparkles size={11} aria-hidden />
          现推假设
        </span>
      </div>

      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodeClick={onNodeClick}
        onEdgeClick={(_, edge) => {
          // 工单 T4：点边 = 打开相邻反应节点详情（用户裁定方案②）
          const raw = edgeById.get(edge.id);
          if (!raw) return;
          const adj = vis.nodes.find(
            (n) => n.type === "reaction" && (n.id === raw.source || n.id === raw.target)
          );
          if (adj) setDrawer({ kind: "reaction", rxn: adj as VisRxnNode });
        }}
        fitView
        minZoom={0.2}
        maxZoom={2}
        nodesDraggable={false}
        panOnDrag={!locked}
        zoomOnScroll={!locked}
        zoomOnPinch={!locked}
        zoomOnDoubleClick={!locked}
        proOptions={{ hideAttribution: true }}
      >
        <Background />
        <Controls showInteractive={false}>
          <ControlButton
            onClick={() => setLocked((v) => !v)}
            aria-label={locked ? "解锁画布" : "锁定画布"}
            title={locked ? "解锁画布（恢复平移缩放）" : "锁定画布（冻结平移缩放）"}
            data-testid={locked ? "canvas-unlock" : "canvas-lock"}
          >
            {locked ? <Lock size={16} aria-hidden /> : <LockOpen size={16} aria-hidden />}
          </ControlButton>
        </Controls>
      </ReactFlow>
      <NodeDrawer selection={drawer} onClose={() => setDrawer(null)} />
    </div>
  );
}

function byIdLookup(vis: Visualization, id: string): VisMolNode | VisRxnNode | undefined {
  return vis.nodes.find((n) => n.id === id) as VisMolNode | VisRxnNode | undefined;
}
