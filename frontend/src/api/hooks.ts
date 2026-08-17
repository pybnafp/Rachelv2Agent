import { useQuery } from "@tanstack/react-query";
import { apiGet } from "./client";
import type { JobOut, ResultOut } from "../types";

export const useJobs = () =>
  useQuery<JobOut[]>({ queryKey: ["jobs"], queryFn: () => apiGet<JobOut[]>("/api/jobs") });

export const useJobResult = (id: string | undefined) =>
  useQuery<ResultOut>({
    queryKey: ["job", id],
    queryFn: () => apiGet<ResultOut>(`/api/jobs/${id}/result`),
    enabled: !!id,
  });
