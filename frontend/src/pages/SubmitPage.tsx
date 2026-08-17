import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, apiGet, ApiError } from "../api/client";
import { useAuthStore } from "../stores/auth";
import { getRDKit } from "../rdkit";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { Input } from "../components/ui/Input";
import { MoleculeView } from "../components/MoleculeView";

const EXAMPLES: Array<{ label: string; smiles: string }> = [
  { label: "阿司匹林", smiles: "CC(=O)OC1=CC=CC=C1C(=O)O" },
  { label: "扑热息痛", smiles: "CC(=O)Nc1ccc(O)cc1" },
  { label: "苯", smiles: "c1ccccc1" },
];

type Validity = "empty" | "valid" | "invalid";

interface LLMProvider {
  name: string;
  model: string;
  is_active: boolean;
}

function validityClass(v: Validity): string {
  if (v === "valid") return "text-emerald-600";
  if (v === "invalid") return "text-red-600";
  return "text-slate-400";
}

function validityText(v: Validity): string {
  if (v === "valid") return "✓ 有效";
  if (v === "invalid") return "✗ 无效 SMILES";
  return "输入 SMILES 开始预览";
}

function AdvancedPanel() {
  const me = useQuery({
    queryKey: ["me"],
    queryFn: () => apiGet<{ username: string; role: string }>("/api/auth/me"),
    retry: false,
  });
  const isAdmin = me.data?.role === "admin" && !(me.error instanceof ApiError);
  const providers = useQuery({
    queryKey: ["llm-providers"],
    queryFn: () => apiGet<LLMProvider[]>("/api/admin/llm-providers"),
    enabled: !!isAdmin,
    retry: false,
  });
  if (!isAdmin) return null;
  return (
    <Card className="w-1/3">
      <details>
        <summary className="cursor-pointer text-sm font-semibold text-slate-700">高级</summary>
        <div className="mt-3" data-testid="llm-providers">
          <div className="mb-2 text-xs font-medium text-slate-500">LLM 供应商（只读）</div>
          {providers.isLoading && <div className="text-xs text-slate-400">加载中…</div>}
          {providers.isError && <div className="text-xs text-red-500">无法加载供应商列表</div>}
          {providers.data?.map((p) => (
            <div key={p.name} className="flex items-center justify-between py-1 text-sm">
              <span>{p.name}</span>
              <span className="text-xs text-slate-500">{p.model}</span>
              <Badge color={p.is_active ? "emerald" : "slate"}>
                {p.is_active ? "active" : "disabled"}
              </Badge>
            </div>
          ))}
        </div>
      </details>
    </Card>
  );
}

export default function SubmitPage() {
  const [name, setName] = useState("");
  const [smiles, setSmiles] = useState("");
  const [validity, setValidity] = useState<Validity>("empty");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  useEffect(() => {
    const pre = searchParams.get("smiles");
    if (pre) {
      setSmiles(pre); // 触发一次有效性判定（上方 effect）
      setSearchParams({}, { replace: true }); // 清掉参数，避免刷新重复填充
    }
    // 仅 mount 时执行一次
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const token = useAuthStore((s) => s.token);
  void token; // AdvancedPanel queries /api/auth/me itself

  useEffect(() => {
    if (smiles === "") {
      setValidity("empty");
      return;
    }
    const t = setTimeout(() => {
      getRDKit()
        .then((RDKit) => {
          const mol = RDKit.get_mol(smiles);
          const ok = !!mol && mol.is_valid();
          mol?.delete();
          setValidity(ok ? "valid" : "invalid");
        })
        .catch(() => setValidity("invalid"));
    }, 300);
    return () => clearTimeout(t);
  }, [smiles]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (busy) return;
    setError(null);
    setBusy(true);
    try {
      const resp = await api<{ id: string }>("/api/jobs", { method: "POST", json: { smiles, name } });
      navigate(`/jobs/${resp.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "网络错误，请稍后再试");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div data-testid="page-submit" className="min-h-screen bg-slate-50 p-6">
      {error && (
        <div
          data-testid="submit-error"
          className="mx-auto mb-4 max-w-4xl rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600"
        >
          {error}
        </div>
      )}
      <div className="mx-auto flex max-w-4xl gap-4">
        <Card className="w-2/3" title="提交任务">
          <form onSubmit={onSubmit} className="flex flex-col gap-3">
            <Input label="任务名（可选）" value={name} onChange={(e) => setName(e.target.value)} />
            <div className="flex flex-col gap-1">
              <label htmlFor="smiles-input" className="text-xs font-medium text-slate-600">
                SMILES
              </label>
              <textarea
                id="smiles-input"
                rows={3}
                value={smiles}
                onChange={(e) => setSmiles(e.target.value)}
                className="rounded-md border border-slate-300 px-3 py-2 font-mono text-sm outline-none focus:ring-2 focus:ring-sky-400"
              />
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-400">示例：</span>
              {EXAMPLES.map((ex) => (
                <Button key={ex.label} type="button" size="sm" variant="outline" onClick={() => setSmiles(ex.smiles)}>
                  {ex.label}
                </Button>
              ))}
            </div>
            <div className={`text-sm font-medium ${validityClass(validity)}`} data-testid="validity">
              {validityText(validity)}
            </div>
            <MoleculeView smiles={smiles} width={320} height={200} />
            <Button type="submit" disabled={busy}>
              {busy ? "提交中…" : "提交"}
            </Button>
          </form>
        </Card>
        <AdvancedPanel />
      </div>
    </div>
  );
}
