import type { Visualization } from "../types";

export interface Positioned {
  x: number;
  y: number;
}

const X_GAP = 240;
const Y_GAP = 170;
const RXN_DY = 85;

export function treeLayout(vis: Visualization): Map<string, Positioned> {
  const children = new Map<string, string[]>();
  for (const e of vis.edges) {
    if (!children.has(e.source)) children.set(e.source, []);
    children.get(e.source)!.push(e.target);
  }
  const byId = new Map(vis.nodes.map((n) => [n.id, n]));
  const positions = new Map<string, Positioned>();
  let slot = 0;
  const visited = new Set<string>();
  const dfs = (id: string) => {
    if (visited.has(id)) return;
    visited.add(id);
    const node = byId.get(id);
    if (!node) return;
    const isRxn = node.type === "reaction";
    positions.set(id, {
      x: slot * X_GAP,
      y: node.depth * Y_GAP + (isRxn ? RXN_DY : 0),
    });
    if (!isRxn) slot += 1; // reaction nodes share the slot of their product, no horizontal space
    for (const c of children.get(id) ?? []) dfs(c);
  };
  const roots = vis.nodes.filter((n) => n.type === "molecule" && n.role === "target");
  roots.forEach((r) => dfs(r.id));
  vis.nodes.forEach((n) => {
    if (!visited.has(n.id)) dfs(n.id);
  }); // orphan fallback
  // center: shift all x by -maxX/2
  const xs = [...positions.values()].map((p) => p.x);
  const shift = xs.length ? Math.max(...xs) / 2 : 0;
  positions.forEach((p) => (p.x -= shift));
  return positions;
}
