import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { Tabs } from "../components/ui/Tabs";
import { StatusBadge } from "../components/StatusBadge";
import { MoleculeView } from "../components/MoleculeView";
import { useJob, useResult } from "../api/hooks";
import { formatDuration } from "../lib/format";

const TABS = [
  { key: "tree", label: "路线树" },
  { key: "report", label: "报告" },
  { key: "files", label: "文件" },
];

export default function JobDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: job, isLoading, isError } = useJob(id);
  const hasResult = job?.status === "succeeded" || job?.status === "partial";
  const { data: result } = useResult(id, !!hasResult);
  const [active, setActive] = useState("tree");

  if (isLoading) {
    return (
      <div data-testid="page-job-detail" className="mx-auto max-w-4xl px-4 py-6">
        <p className="py-12 text-center text-sm text-slate-500">加载中…</p>
      </div>
    );
  }

  if (isError || !job) {
    return (
      <div data-testid="page-job-detail" className="mx-auto max-w-4xl px-4 py-6">
        <Card>
          <p className="text-sm text-red-600">任务加载失败或不存在。</p>
          <Link to="/jobs" className="mt-2 inline-block text-sm text-sky-600 hover:underline">
            ← 返回任务列表
          </Link>
        </Card>
      </div>
    );
  }

  return (
    <div data-testid="page-job-detail" className="mx-auto max-w-4xl space-y-4 px-4 py-6">
      <Card>
        <div className="mb-3 flex items-center gap-3">
          <Link to="/jobs" className="text-sm text-sky-600 hover:underline">
            ← 任务列表
          </Link>
          <h1 className="text-lg font-semibold text-slate-800">{job.name || "(未命名)"}</h1>
          <StatusBadge status={job.status} />
        </div>
        <div className="flex flex-col gap-4 sm:flex-row">
          <MoleculeView smiles={job.smiles} width={240} height={160} />
          <div className="min-w-0 flex-1 space-y-2">
            <p className="truncate font-mono text-xs text-slate-600" title={job.smiles}>
              {job.smiles}
            </p>
            <p className="text-xs text-slate-500">
              steps: {job.stats.steps ?? 0} · tokens_in: {job.stats.tokens_in ?? 0} · tokens_out:{" "}
              {job.stats.tokens_out ?? 0} · 耗时: {formatDuration(job.started_at, job.finished_at)} · 创建于:{" "}
              {new Date(job.created_at).toLocaleString()}
            </p>
            {job.status === "partial" && job.stats.reason != null && (
              <p className="text-xs text-amber-600">原因：{String(job.stats.reason)}</p>
            )}
          </div>
        </div>
        {job.status === "failed" && (
          <pre
            data-testid="job-error"
            className="mt-3 whitespace-pre-wrap rounded-md bg-red-50 p-3 text-xs text-red-700"
          >
            {job.error}
          </pre>
        )}
      </Card>

      {(job.status === "queued" || job.status === "running") && (
        <Card>
          <div data-testid="running-hint" className="space-y-1 text-sm text-slate-600">
            <p>任务执行中，预计 10-30 分钟。</p>
            <p>
              当前进度：{job.stats.steps ?? 0} 步。页面将自动刷新，无需手动操作。
            </p>
          </div>
        </Card>
      )}

      {hasResult && (
        <div className="space-y-3">
          <Tabs tabs={TABS} active={active} onChange={setActive} />
          <div data-testid="tab-tree" hidden={active !== "tree"} className="rounded-lg border border-dashed border-slate-300 p-8 text-center text-sm text-slate-400">
            路线树将在此渲染
          </div>
          <div data-testid="tab-report" hidden={active !== "report"} className="rounded-lg border border-dashed border-slate-300 p-8 text-center text-sm text-slate-400">
            报告将在此嵌入
          </div>
          <div data-testid="tab-files" hidden={active !== "files"}>
            <Card title="产物指标">
              {result?.metrics ? (
                <dl className="grid grid-cols-3 gap-4 text-sm">
                  <div>
                    <dt className="text-xs text-slate-500">n_nodes</dt>
                    <dd className="font-semibold text-slate-800">{String(result.metrics.n_nodes)}</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-slate-500">n_edges</dt>
                    <dd className="font-semibold text-slate-800">{String(result.metrics.n_edges)}</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-slate-500">n_terminals</dt>
                    <dd className="font-semibold text-slate-800">{String(result.metrics.n_terminals)}</dd>
                  </div>
                </dl>
              ) : (
                <p className="text-sm text-slate-500">产物不完整</p>
              )}
            </Card>
          </div>
        </div>
      )}

      {job.status === "cancelled" && (
        <Card>
          <p className="mb-3 text-sm text-slate-600">该任务已取消。</p>
          <Button variant="primary" size="sm" onClick={() => navigate(`/?smiles=${encodeURIComponent(job.smiles)}`)}>
            重新提交
          </Button>
        </Card>
      )}
    </div>
  );
}
