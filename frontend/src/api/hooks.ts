import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, apiGet } from "./client";
import { useAuthStore } from "../stores/auth";
import type { JobOut, ResultOut, TraceStep } from "../types";

const TERMINAL_STATUSES = new Set(["succeeded", "partial", "failed", "cancelled"]);
const POLL_INTERVAL_MS = 3000;

export interface JobEventsOpts {
  id: string | undefined;
  onSteps: (steps: TraceStep[], replace: boolean) => void;
  onStatus?: (s: { status: string; stats: Record<string, any> }) => void;
  onDone?: (status: string) => void;
}

/**
 * 订阅 /api/jobs/{id}/events SSE（snapshot/steps/status/done）；
 * 连接失败时降级为 3s 轮询 /trace?after=lastSeq + GET job。
 */
export function useJobEvents(opts: JobEventsOpts): { mode: "sse" | "polling" | "closed" } {
  const token = useAuthStore((s) => s.token);
  const id = opts.id;
  const [mode, setMode] = useState<"sse" | "polling" | "closed">("closed");
  const optsRef = useRef(opts);
  optsRef.current = opts;

  useEffect(() => {
    if (!id || !token) {
      setMode("closed");
      return;
    }
    setMode("sse");
    const state = { lastSeq: 0, terminal: false, finished: false };
    let es: EventSource | null = null;
    let timer: ReturnType<typeof setInterval> | null = null;

    const finish = (status: string) => {
      state.terminal = true;
      es?.close();
      es = null;
      if (timer) {
        clearInterval(timer);
        timer = null;
      }
      if (!state.finished) {
        state.finished = true;
        setMode("closed");
        optsRef.current.onDone?.(status);
      }
    };

    const handleSteps = (steps: TraceStep[], replace: boolean) => {
      optsRef.current.onSteps(steps, replace);
      const last = steps[steps.length - 1];
      if (last) state.lastSeq = Math.max(state.lastSeq, last.seq);
    };

    const startPolling = () => {
      if (state.terminal || timer) return;
      setMode("polling");
      const tick = async () => {
        if (state.terminal) return;
        try {
          const trace = await apiGet<{ steps: TraceStep[] }>(`/api/jobs/${id}/trace?after=${state.lastSeq}`);
          handleSteps(trace.steps ?? [], false);
          const job = await apiGet<JobOut>(`/api/jobs/${id}`);
          optsRef.current.onStatus?.({ status: job.status, stats: job.stats });
          if (TERMINAL_STATUSES.has(job.status)) finish(job.status);
        } catch {
          // 网络抖动：下一轮继续
        }
      };
      void tick();
      timer = setInterval(() => void tick(), POLL_INTERVAL_MS);
    };

    es = new EventSource(`/api/jobs/${id}/events?token=${encodeURIComponent(token)}`);
    es.addEventListener("snapshot", (ev) => {
      const p = JSON.parse((ev as MessageEvent).data);
      if (p.stats_live?.last_seq != null) state.lastSeq = Math.max(state.lastSeq, p.stats_live.last_seq);
      handleSteps(p.steps ?? [], true);
      if (TERMINAL_STATUSES.has(p.status)) finish(p.status);
    });
    es.addEventListener("steps", (ev) => {
      const p = JSON.parse((ev as MessageEvent).data);
      handleSteps(p.steps ?? [], false);
    });
    es.addEventListener("status", (ev) => {
      const p = JSON.parse((ev as MessageEvent).data);
      optsRef.current.onStatus?.(p);
      if (TERMINAL_STATUSES.has(p.status)) finish(p.status);
    });
    es.addEventListener("done", (ev) => {
      const p = JSON.parse((ev as MessageEvent).data);
      finish(p.status ?? "succeeded");
    });
    es.onerror = () => {
      if (state.terminal) return;
      es?.close();
      es = null;
      startPolling();
    };

    return () => {
      es?.close();
      if (timer) clearInterval(timer);
    };
  }, [id, token]);

  return { mode };
}

export const useJobs = () =>
  useQuery<JobOut[]>({
    queryKey: ["jobs"],
    queryFn: () => apiGet<JobOut[]>("/api/jobs?mine=1"),
    refetchInterval: (q) =>
      q.state.data?.some((j) => j.status === "queued" || j.status === "running") ? 3000 : false,
  });

export const useJob = (id: string | undefined) =>
  useQuery<JobOut>({
    queryKey: ["job", id],
    queryFn: () => apiGet<JobOut>(`/api/jobs/${id}`),
    enabled: !!id,
    refetchInterval: (q) =>
      q.state.data && (q.state.data.status === "queued" || q.state.data.status === "running") ? 3000 : false,
  });

export const useResult = (id: string | undefined, enabled: boolean) =>
  useQuery<ResultOut>({
    queryKey: ["result", id],
    queryFn: () => apiGet<ResultOut>(`/api/jobs/${id}/result`),
    enabled: !!id && enabled,
  });

export const useTrace = (id: string | undefined, enabled: boolean) =>
  useQuery<{ steps: TraceStep[] }>({
    queryKey: ["trace", id],
    queryFn: () => apiGet<{ steps: TraceStep[] }>(`/api/jobs/${id}/trace`),
    enabled: !!id && enabled,
  });

export const useSubmit = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { smiles: string; name?: string }) => api<JobOut>("/api/jobs", { method: "POST", json: body }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["jobs"] });
    },
  });
};

export const useCancel = (id: string) => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api<JobOut>(`/api/jobs/${id}/cancel`, { method: "POST" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["jobs"] });
      qc.invalidateQueries({ queryKey: ["job", id] });
    },
  });
};

export const useDelete = (id: string) => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api<void>(`/api/jobs/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["jobs"] });
    },
  });
};
