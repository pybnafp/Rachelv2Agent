import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Download, ExternalLink, RotateCcw } from "lucide-react";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { Skeleton } from "../components/ui/Skeleton";
import { Tabs } from "../components/ui/Tabs";
import { StatusBadge } from "../components/StatusBadge";
import { MoleculeView } from "../components/MoleculeView";
import { useJob, useResult } from "../api/hooks";
import { useAuthStore } from "../stores/auth";
import { formatDuration } from "../lib/format";
import RouteTreeCanvas from "../components/RouteTreeCanvas";
import { AuditTimeline } from "../components/AuditTimeline";
import { TerminalAuditPanel } from "../components/TerminalAuditPanel";
import { ProgressPanel } from "../components/ProgressPanel";

const TABS = [
  { key: "tree", label: "路线树" },
  { key: "report", label: "报告" },
  { key: "audit", label: "决策审计" },
  { key: "terminals", label: "终点审计" },
  { key: "files", label: "文件" },
];

// iframe/<a>/<img> 无法携带 Authorization 头 → 走后端 ?token= 双通道（M2-T10 裁定）
const ARTIFACTS = [
  { path: "export/report.txt", name: "report.txt", label: "报告文本" },
  { path: "export/tree.json", name: "tree.json", label: "合成树JSON" },
  { path: "export/terminals.json", name: "terminals.json", label: "起始原料" },
  { path: "export/visualization.json", name: "visualization.json", label: "可视化数据" },
  { path: "export/session.json", name: "session.json", label: "会话快照" },
  { path: "export/terminal_audit.json", name: "terminal_audit.json", label: "终点审计数据" },
  { path: "messages.jsonl", name: "messages.jsonl", label: "消息日志" },
  { path: "session.json", name: "session.json", label: "任务会话" },
];

export default function JobDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { data: job, isLoading, isError } = useJob(id);
  const hasResult = job?.status === "succeeded" || job?.status === "partial";
  const { data: result } = useResult(id, !!hasResult);
  const [active, setActive] = useState("tree");
  // 终点审计在状态翻转之后数秒才落盘（设计上不阻塞结果展示）→ 成功态且 audit 未返回时限时轮询补抓
  useEffect(() => {
    if (!hasResult || result?.terminal_audit) return;
    const tick = setInterval(() => qc.invalidateQueries({ queryKey: ["result", id] }), 5000);
    const stop = setTimeout(() => clearInterval(tick), 60_000);
    return () => {
      clearInterval(tick);
      clearTimeout(stop);
    };
  }, [hasResult, result?.terminal_audit?.available, id, qc]);
  const token = useAuthStore((s) => s.token) ?? "";
  const fileUrl = (p: string) => `/api/jobs/${id}/files/${p}?token=${encodeURIComponent(token)}`;
  const reportUrl = fileUrl("export/SYNTHESIS_REPORT.html");

  if (isLoading) {
    return (
      <div data-testid="page-job-detail" className="mx-auto max-w-4xl space-y-4 px-4 py-6">
        <Card data-testid="detail-skeleton">
          <div className="mb-3 space-y-2">
            <Skeleton className="h-4 w-40" />
          </div>
          <div className="flex flex-col gap-4 sm:flex-row">
            <Skeleton className="h-[160px] w-[240px]" />
            <div className="min-w-0 flex-1 space-y-2">
              <Skeleton className="h-3 w-2/3" />
              <Skeleton className="h-3 w-1/2" />
              <Skeleton className="h-3 w-1/3" />
            </div>
          </div>
        </Card>
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
          <Link to="/jobs" className="inline-flex items-center gap-1 text-sm text-sky-600 hover:underline">
            <ArrowLeft size={14} aria-hidden />
            任务列表
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
        <ProgressPanel
          jobId={id!}
          onTerminal={() => {
            qc.invalidateQueries({ queryKey: ["job", id] });
            qc.invalidateQueries({ queryKey: ["result", id] });
          }}
        />
      )}

      {hasResult && (
        <div className="space-y-3">
          <Tabs tabs={TABS} active={active} onChange={setActive} />
          <div data-testid="tab-tree" hidden={active !== "tree"}>
            {result?.visualization?.nodes?.length ? (
              <RouteTreeCanvas vis={result.visualization} />
            ) : (
              <div className="rounded-lg border border-dashed border-slate-300 p-8 text-center text-sm text-slate-400">
                产物不完整
              </div>
            )}
          </div>
          <div data-testid="tab-report" hidden={active !== "report"} className="space-y-3">
            <div data-testid="metrics-dashboard" className="grid grid-cols-2 gap-3 sm:grid-cols-5">
              <div className="rounded-xl bg-surface-2 p-3 text-center">
                <p className="text-xs text-slate-500">路线步数</p>
                <p data-testid="metric-steps" className="text-2xl font-semibold text-slate-800">
                  {String(job.stats.steps ?? 0)}
                </p>
              </div>
              <div className="rounded-xl bg-surface-2 p-3 text-center">
                <p className="text-xs text-slate-500">起始原料</p>
                <p data-testid="metric-terminals" className="text-2xl font-semibold text-slate-800">
                  {String(result?.metrics?.n_terminals ?? "—")}
                </p>
              </div>
              <div className="rounded-xl bg-surface-2 p-3 text-center">
                <p className="text-xs text-slate-500">tokens 输入</p>
                <p data-testid="metric-tokens-in" className="text-2xl font-semibold text-slate-800">
                  {(job.stats.tokens_in ?? 0).toLocaleString()}
                </p>
              </div>
              <div className="rounded-xl bg-surface-2 p-3 text-center">
                <p className="text-xs text-slate-500">tokens 输出</p>
                <p data-testid="metric-tokens-out" className="text-2xl font-semibold text-slate-800">
                  {(job.stats.tokens_out ?? 0).toLocaleString()}
                </p>
              </div>
              <div className="rounded-xl bg-surface-2 p-3 text-center">
                <p className="text-xs text-slate-500">耗时</p>
                <p data-testid="metric-duration" className="text-2xl font-semibold text-slate-800">
                  {formatDuration(job.started_at, job.finished_at)}
                </p>
              </div>
            </div>
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium text-slate-700">合成报告</p>
              <a
                data-testid="report-open"
                href={reportUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-sm text-sky-600 hover:underline"
              >
                <ExternalLink size={13} aria-hidden />
                新窗口打开
              </a>
            </div>
            <iframe
              data-testid="report-iframe"
              title="synthesis report"
              src={reportUrl}
              // 不带 allow-same-origin：报告在 opaque origin 中运行，读不到本站
              // localStorage/cookie（?token= 泄露面最小化）；allow-scripts 保留图表脚本，
              // 静态子资源（图片等）加载不受影响。
              sandbox="allow-scripts"
              className="w-full h-[70vh] rounded border bg-white"
            />
          </div>
          <div data-testid="tab-audit" hidden={active !== "audit"}>
            <AuditTimeline jobId={id} jobStatus={job.status} />
          </div>
          <div data-testid="tab-terminals" hidden={active !== "terminals"}>
            <TerminalAuditPanel terminals={result?.terminals} audit={result?.terminal_audit ?? null} />
          </div>
          <div data-testid="tab-files" hidden={active !== "files"} className="space-y-3">
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
            <Card title="产物文件下载">
              <ul className="divide-y divide-slate-100">
                {ARTIFACTS.map((f) => (
                  <li key={f.path} className="flex items-center justify-between py-2">
                    <a
                      data-testid={`dl-${f.name}`}
                      href={fileUrl(f.path)}
                      download
                      className="inline-flex items-center gap-1 font-mono text-sm text-sky-600 hover:underline"
                    >
                      <Download size={12} aria-hidden />
                      {f.name}
                    </a>
                    <span className="text-xs text-slate-500">{f.label}</span>
                  </li>
                ))}
              </ul>
              <p className="mt-2 text-xs text-slate-400">文件不存在时下载会失败。</p>
            </Card>
          </div>
        </div>
      )}

      {job.status === "cancelled" && (
        <Card>
          <p className="mb-3 text-sm text-slate-600">该任务已取消。</p>
          <Button variant="primary" size="sm" onClick={() => navigate(`/?smiles=${encodeURIComponent(job.smiles)}`)}>
            <span className="inline-flex items-center gap-1">
              <RotateCcw size={13} aria-hidden />
              重新提交
            </span>
          </Button>
        </Card>
      )}
    </div>
  );
}
