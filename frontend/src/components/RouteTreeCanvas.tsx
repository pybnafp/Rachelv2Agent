import { useEffect, useMemo, useState } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  MarkerType,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { VisEdge, VisMolNode, VisRxnNode, Visualization } from "../types";
import { treeLayout } from "../lib/treeLayout";
import { MoleculeView } from "./MoleculeView";
import { NodeDrawer, type DrawerSelection } from "./NodeDrawer";

const ROLE_STYLE: Record<VisMolNode["role"], string> = {
  target: "border-blue-600 bg-blue-50",
  intermediate: "border-slate-400 bg-white",
  terminal: "border-emerald-600 bg-emerald-50",
};

const ROLE_BADGE: Record<VisMolNode["role"], string> = {
  target: "bg-blue-600 text-white",
  intermediate: "bg-slate-200 text-slate-700",
  terminal: "bg-emerald-600 text-white",
};

function MoleculeCard({ data }: { data: VisMolNode }) {
  return (
    <div
      data-testid={`mol-card-${data.id}`}
      className={`w-44 overflow-hidden rounded-lg border-2 shadow-sm ${ROLE_STYLE[data.role] ?? ROLE_STYLE.intermediate}`}
    >
      <div className="flex items-center justify-center bg-white p-1">
        <MoleculeView smiles={data.smiles} width={160} height={110} />
      </div>
      <div className="flex items-center justify-between gap-1 px-2 py-1">
        <span
          className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${ROLE_BADGE[data.role] ?? ROLE_BADGE.intermediate}`}
        >
          {data.role}
        </span>
        <span className="text-[10px] font-mono text-slate-600">
          {data.cs_score != null ? data.cs_score.toFixed(2) : "—"}
        </span>
      </div>
    </div>
  );
}

function ReactionPill({ data }: { data: VisRxnNode }) {
  const label = data.label.length > 18 ? `${data.label.slice(0, 18)}…` : data.label;
  return (
    <div
      data-testid={`rxn-pill-${data.id}`}
      title={data.label}
      className="cursor-pointer rounded-full border border-amber-500 bg-amber-100 px-3 py-1 text-xs text-amber-900"
    >
      {label}
    </div>
  );
}

type MolFlowNode = Node<{ mol: VisMolNode }, "molecule">;
type RxnFlowNode = Node<{ rxn: VisRxnNode }, "reaction">;

export default function RouteTreeCanvas({ vis }: { vis: Visualization }) {
  const [drawer, setDrawer] = useState<DrawerSelection>(null);
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
      markerEnd: { type: MarkerType.ArrowClosed },
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
      reaction: (props: NodeProps<RxnFlowNode>) => <ReactionPill data={props.data.rxn} />,
    }),
    []
  );

  return (
    <div className="relative h-[600px] w-full overflow-hidden rounded-lg border border-slate-200" data-testid="route-tree-canvas">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodeClick={onNodeClick}
        onEdgeClick={(_, edge) => {
          const raw = edgeById.get(edge.id);
          if (raw) setDrawer({ kind: "edge", edge: raw, nodes: vis.nodes });
        }}
        fitView
        minZoom={0.2}
        maxZoom={2}
        nodesDraggable={false}
        proOptions={{ hideAttribution: true }}
      >
        <Background />
        <Controls />
        <MiniMap pannable zoomable />
      </ReactFlow>
      <NodeDrawer selection={drawer} onClose={() => setDrawer(null)} />
    </div>
  );
}

function byIdLookup(vis: Visualization, id: string): VisMolNode | VisRxnNode | undefined {
  return vis.nodes.find((n) => n.id === id) as VisMolNode | VisRxnNode | undefined;
}
