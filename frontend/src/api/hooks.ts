import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, apiGet } from "./client";
import type { JobOut, ResultOut } from "../types";

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
