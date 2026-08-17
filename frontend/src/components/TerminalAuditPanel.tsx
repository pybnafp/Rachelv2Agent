import { Badge } from "./ui/Badge";
import { Card } from "./ui/Card";
import { MoleculeView } from "./MoleculeView";
import type { TerminalAudit } from "../types";

interface TerminalRow {
  node_id: string;
  smiles: string;
  cs_score?: number | null;
  [key: string]: any;
}

function cidLink(r: TerminalRow) {
  const best = r.pubchem?.best_cid;
  const url = r.pubchem?.best_cid_url;
  if (best != null && url) {
    return (
      <a href={url} target="_blank" rel="noreferrer" className="font-mono text-sm text-sky-600 hover:underline">
        CID {best}
      </a>
    );
  }
  return <span className="text-sm text-slate-400">—</span>;
}

export function TerminalAuditPanel({
  terminals,
  audit,
}: {
  terminals: TerminalRow[] | undefined;
  audit: TerminalAudit | null | undefined;
}) {
  const rows: TerminalRow[] = terminals ?? [];
  const available = audit?.available === true;
  const results = audit?.results ?? [];
  const byNode = new Map<string, any>(results.map((r) => [r.node_id, r]));

  let cidClosed = 0;
  let vendorClosed = 0;
  if (available) {
    for (const r of results) {
      if (r.pubchem_metrics?.pubchem_cid_closed) cidClosed++;
      if (r.pubchem_metrics?.vendor_closed) vendorClosed++;
    }
  }
  const summary = audit?.summary ?? {};
  // 仅当 summary 缺键时才回退到 results 计数（单一取值路径）
  const cid = summary.pubchem_cid_closed ?? cidClosed;
  const vendor = summary.vendor_closed ?? vendorClosed;
  const total = summary.total_terminals ?? results.length;
  const cidText = `${cid}/${total} CID 闭合`;
  const vendorText = `${vendor}/${total} Vendor 闭合`;

  return (
    <div className="space-y-3" data-testid="terminal-audit-panel">
      {!(audit?.available === true) ? (
        <div
          data-testid="audit-unavailable"
          className="rounded-md border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-800"
        >
          <p className="font-medium">终点审计不可用</p>
          {audit?.error && <p className="mt-1 text-xs text-amber-700">{audit.error}</p>}
        </div>
      ) : (
        <div data-testid="audit-summary" className="flex flex-wrap items-center gap-x-6 gap-y-1 rounded-md border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-slate-700">
          <span className="font-medium">{cidText}</span>
          <span className="font-medium">{vendorText}</span>
          {audit.offline && <span className="text-xs text-slate-500">离线审计（本地分类）</span>}
        </div>
      )}

      <Card title="终点列表">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-xs text-slate-500">
                <th className="py-2 pr-3 font-medium">结构</th>
                <th className="py-2 pr-3 font-medium">SMILES</th>
                <th className="py-2 pr-3 font-medium">CS</th>
                {available && <th className="py-2 pr-3 font-medium">CID</th>}
                {available && <th className="py-2 pr-3 font-medium">闭合</th>}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const a = byNode.get(r.node_id);
                const cidClosed = !!a?.pubchem_metrics?.pubchem_cid_closed;
                const vendorClosed = !!a?.pubchem_metrics?.vendor_closed;
                const cs = r.cs_score ?? a?.cs_score;
                return (
                  <tr key={r.node_id} data-testid={`terminal-row-${r.node_id}`} className="border-b border-slate-100 align-middle">
                    <td className="py-2 pr-3">
                      <MoleculeView smiles={r.smiles} width={120} height={80} />
                    </td>
                    <td className="max-w-52 py-2 pr-3">
                      <span className="block truncate font-mono text-xs text-slate-700" title={r.smiles}>
                        {r.smiles}
                      </span>
                      {a?.allowlist?.hit && (
                        <Badge data-testid={`allowlist-badge-${r.node_id}`} color="amber" className="mt-1">
                          allowlist
                        </Badge>
                      )}
                    </td>
                    <td className="py-2 pr-3 font-mono text-xs text-slate-700">
                      {typeof cs === "number" ? cs.toFixed(2) : "—"}
                    </td>
                    {available && <td className="py-2 pr-3">{cidLink(a ?? r)}</td>}
                    {available && (
                      <td className="py-2 pr-3">
                        <span className="flex flex-wrap gap-1">
                          <Badge data-testid={`cid-badge-${r.node_id}`} color={cidClosed ? "emerald" : "slate"}>
                            {cidClosed ? "CID✓" : "CID✗"}
                          </Badge>
                          <Badge data-testid={`vendor-badge-${r.node_id}`} color={vendorClosed ? "emerald" : "slate"}>
                            {vendorClosed ? "Vendor✓" : "Vendor✗"}
                          </Badge>
                        </span>
                      </td>
                    )}
                  </tr>
                );
              })}
              {rows.length === 0 && (
                <tr>
                  <td colSpan={available ? 5 : 3} className="py-6 text-center text-sm text-slate-400">
                    暂无终点数据
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
