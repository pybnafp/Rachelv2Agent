import { Link, useNavigate } from "react-router-dom";
import { Button } from "../components/ui/Button";
import { StatusBadge } from "../components/StatusBadge";
import { MoleculeView } from "../components/MoleculeView";
import { useJobs, useCancel, useDelete } from "../api/hooks";
import { formatDuration } from "../lib/format";
import type { JobOut } from "../types";

function truncate(s: string, n: number) {
  return s.length > n ? s.slice(0, n) + "…" : s;
}

function JobRow({ job }: { job: JobOut }) {
  const cancel = useCancel(job.id);
  const del = useDelete(job.id);
  const canCancel = job.status === "queued" || job.status === "running";
  return (
    <tr>
      <td className="px-3 py-2 text-sm text-slate-800">{job.name || "(未命名)"}</td>
      <td className="px-3 py-2">
        <MoleculeView smiles={job.smiles} width={120} height={80} />
      </td>
      <td className="px-3 py-2 font-mono text-xs text-slate-600" title={job.smiles}>
        {truncate(job.smiles, 40)}
      </td>
      <td className="px-3 py-2">
        <StatusBadge status={job.status} />
      </td>
      <td className="px-3 py-2 text-xs text-slate-600">
        {(job.stats.steps ?? 0) as number} 步 · {formatDuration(job.started_at, job.finished_at)}
      </td>
      <td className="px-3 py-2 text-xs text-slate-500">
        {new Date(job.created_at).toLocaleString()}
      </td>
      <td className="px-3 py-2">
        <div className="flex gap-2">
          <Link to={`/jobs/${job.id}`}>
            <Button variant="primary" size="sm">
              查看
            </Button>
          </Link>
          {canCancel && (
            <Button
              variant="outline"
              size="sm"
              disabled={cancel.isPending}
              onClick={() => {
                if (window.confirm("确定取消该任务？")) cancel.mutate();
              }}
            >
              取消
            </Button>
          )}
          <Button
            variant="danger"
            size="sm"
            disabled={del.isPending}
            onClick={() => {
              if (window.confirm("确定删除该任务？")) del.mutate();
            }}
          >
            删除
          </Button>
        </div>
      </td>
    </tr>
  );
}

export default function JobsPage() {
  const navigate = useNavigate();
  const { data: jobs, isLoading } = useJobs();

  return (
    <div data-testid="page-jobs" className="mx-auto max-w-5xl px-4 py-6">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-lg font-semibold text-slate-800">我的任务</h1>
        <Button variant="primary" size="sm" onClick={() => navigate("/")}>
          提交任务
        </Button>
      </div>

      {isLoading ? (
        <div className="py-12 text-center text-sm text-slate-500">加载中…</div>
      ) : !jobs || jobs.length === 0 ? (
        <div className="flex flex-col items-center gap-3 py-16">
          <p className="text-sm text-slate-500">还没有任务</p>
          <Button variant="primary" size="sm" onClick={() => navigate("/")}>
            去提交
          </Button>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white shadow-sm">
          <table className="w-full min-w-[720px]">
            <thead>
              <tr className="border-b border-slate-200 text-left text-xs text-slate-500">
                <th className="px-3 py-2 font-medium">名称</th>
                <th className="px-3 py-2 font-medium">结构</th>
                <th className="px-3 py-2 font-medium">SMILES</th>
                <th className="px-3 py-2 font-medium">状态</th>
                <th className="px-3 py-2 font-medium">进度</th>
                <th className="px-3 py-2 font-medium">创建时间</th>
                <th className="px-3 py-2 font-medium">操作</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((j) => (
                <JobRow key={j.id} job={j} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
