import { describe, expect, it } from "vitest";
import { treeLayout } from "../lib/treeLayout";
import vis from "./fixtures/visualization.json";
import type { Visualization } from "../types";

const visualization = vis as unknown as Visualization;

describe("treeLayout", () => {
  const positions = treeLayout(visualization);

  it("covers all 28 node ids", () => {
    expect(visualization.nodes).toHaveLength(28);
    for (const n of visualization.nodes) {
      expect(positions.has(n.id), `missing position for ${n.id}`).toBe(true);
    }
    expect(positions.size).toBe(28);
  });

  it("places mol_0 at y=0, rxn_1 at y=85, mol_1/mol_2 at y=170", () => {
    expect(positions.get("mol_0")!.y).toBe(0);
    expect(positions.get("rxn_1")!.y).toBe(85); // 0*170 + 85
    expect(positions.get("mol_1")!.y).toBe(170);
    expect(positions.get("mol_2")!.y).toBe(170);
  });

  it("gives molecule nodes at the same depth distinct x", () => {
    const byDepth = new Map<number, Set<number>>();
    for (const n of visualization.nodes) {
      if (n.type !== "molecule") continue;
      const p = positions.get(n.id)!;
      if (!byDepth.has(n.depth)) byDepth.set(n.depth, new Set());
      byDepth.get(n.depth)!.add(p.x);
    }
    for (const [depth, xs] of byDepth) {
      const molsAtDepth = visualization.nodes.filter(
        (n) => n.type === "molecule" && n.depth === depth
      );
      expect(xs.size, `depth ${depth}`).toBe(molsAtDepth.length);
    }
  });

  it("positions both endpoints of every edge", () => {
    expect(visualization.edges.length).toBeGreaterThan(0);
    for (const e of visualization.edges) {
      expect(positions.has(e.source), `missing source ${e.source}`).toBe(true);
      expect(positions.has(e.target), `missing target ${e.target}`).toBe(true);
    }
  });
});
