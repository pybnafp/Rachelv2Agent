import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, apiGet } from "../api/client";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { Input } from "../components/ui/Input";

interface ProviderRow {
  id: number;
  name: string;
  base_url: string;
  model: string;
  temperature: number | null;
  max_output: number | null;
  is_active: boolean;
}

interface ProviderForm {
  name: string;
  base_url: string;
  api_key: string;
  model: string;
  temperature: string;
  max_output: string;
}

const EMPTY_FORM: ProviderForm = {
  name: "",
  base_url: "",
  api_key: "",
  model: "",
  temperature: "",
  max_output: "",
};

function toForm(p: ProviderRow): ProviderForm {
  return {
    name: p.name,
    base_url: p.base_url,
    api_key: "",
    model: p.model,
    temperature: p.temperature != null ? String(p.temperature) : "",
    max_output: p.max_output != null ? String(p.max_output) : "",
  };
}

function ProviderFormCard({
  initial,
  onClose,
}: {
  initial: ProviderForm;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [form, setForm] = useState<ProviderForm>(initial);
  const valid = form.name.trim() !== "" && form.base_url.trim() !== "" && form.model.trim() !== "";
  const save = useMutation({
    mutationFn: () =>
      api("/api/admin/llm-providers", {
        method: "PUT",
        json: {
          name: form.name.trim(),
          base_url: form.base_url.trim(),
          model: form.model.trim(),
          ...(form.api_key ? { api_key: form.api_key } : {}),
          ...(form.temperature !== "" ? { temperature: Number(form.temperature) } : {}),
          ...(form.max_output !== "" ? { max_output: Number(form.max_output) } : {}),
        },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["providers"] });
      onClose();
    },
  });
  const set = (k: keyof ProviderForm) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  return (
    <Card title={initial.name ? `编辑：${initial.name}` : "新增供应商"}>
      <div className="grid gap-3 sm:grid-cols-2">
        <Input label="名称" value={form.name} onChange={set("name")} />
        <Input label="模型" value={form.model} onChange={set("model")} />
        <Input
          label="Base URL"
          value={form.base_url}
          onChange={set("base_url")}
          className="sm:col-span-2"
        />
        <Input
          label="API Key"
          type="password"
          placeholder="留空则不修改"
          value={form.api_key}
          onChange={set("api_key")}
          autoComplete="new-password"
        />
        <div className="grid grid-cols-2 gap-3">
          <Input
            label="temperature"
            type="number"
            step="0.1"
            value={form.temperature}
            onChange={set("temperature")}
          />
          <Input
            label="max_output"
            type="number"
            value={form.max_output}
            onChange={set("max_output")}
          />
        </div>
      </div>
      {!valid && <p className="mt-2 text-xs text-slate-500">名称、Base URL、模型为必填项。</p>}
      {save.isError && (
        <p data-testid="provider-form-error" className="mt-2 rounded bg-red-50 px-3 py-2 text-sm text-red-600">
          {(save.error as Error).message}
        </p>
      )}
      <div className="mt-3 flex gap-2">
        <Button variant="primary" size="sm" disabled={!valid || save.isPending} onClick={() => save.mutate()}>
          保存
        </Button>
        <Button variant="ghost" size="sm" onClick={onClose}>
          取消
        </Button>
      </div>
    </Card>
  );
}

export default function AdminProvidersPage() {
  const qc = useQueryClient();
  const { data: me } = useQuery<{ role: string }>({
    queryKey: ["me"],
    queryFn: () => apiGet<{ role: string }>("/api/auth/me"),
  });
  const { data: providers, isLoading } = useQuery<ProviderRow[]>({
    queryKey: ["providers"],
    queryFn: () => apiGet<ProviderRow[]>("/api/admin/llm-providers"),
    enabled: me?.role === "admin",
  });
  const [form, setForm] = useState<ProviderForm | null>(null);

  const setActive = useMutation({
    mutationFn: (p: ProviderRow) =>
      api("/api/admin/llm-providers", {
        method: "PUT",
        json: {
          name: p.name,
          base_url: p.base_url,
          model: p.model,
          ...(p.temperature != null ? { temperature: p.temperature } : {}),
          ...(p.max_output != null ? { max_output: p.max_output } : {}),
          is_active: true,
        },
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["providers"] }),
  });

  if (me && me.role !== "admin") {
    return (
      <div data-testid="page-admin-providers" className="mx-auto max-w-3xl px-4 py-6">
        <Card>
          <p className="text-sm font-medium text-slate-800">无权限</p>
          <p className="mt-1 text-xs text-slate-500">该页面仅管理员可访问。</p>
          <Link to="/" className="mt-2 inline-block text-sm text-sky-600 hover:underline">
            ← 返回首页
          </Link>
        </Card>
      </div>
    );
  }

  return (
    <div data-testid="page-admin-providers" className="mx-auto max-w-3xl space-y-4 px-4 py-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-slate-800">供应商管理</h1>
        <Button
          variant="primary"
          size="sm"
          onClick={() => setForm({ ...EMPTY_FORM })}
        >
          新增供应商
        </Button>
      </div>

      {form && <ProviderFormCard initial={form} onClose={() => setForm(null)} />}

      {isLoading && <p className="text-sm text-slate-500">加载中…</p>}
      {providers?.map((p) => (
        <Card key={p.id}>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <span className="font-semibold text-slate-800">{p.name}</span>
            {p.is_active && <Badge color="sky">当前使用</Badge>}
          </div>
          <div className="mt-1 space-y-0.5 text-xs text-slate-500">
            <p className="font-mono">{p.model}</p>
            <p className="truncate font-mono" title={p.base_url}>
              {p.base_url}
            </p>
            <p>
              temperature: {p.temperature ?? "—"} · max_output: {p.max_output ?? "—"} · api_key: —
              （提交时留空则不变）
            </p>
          </div>
          <div className="mt-3 flex gap-2">
            <Button variant="ghost" size="sm" onClick={() => setForm(toForm(p))}>
              编辑
            </Button>
            {!p.is_active && (
              <Button
                variant="ghost"
                size="sm"
                disabled={setActive.isPending}
                onClick={() => setActive.mutate(p)}
              >
                设为当前
              </Button>
            )}
          </div>
        </Card>
      ))}
      {setActive.isError && (
        <p className="rounded bg-red-50 px-3 py-2 text-sm text-red-600">
          {(setActive.error as Error).message}
        </p>
      )}
    </div>
  );
}
