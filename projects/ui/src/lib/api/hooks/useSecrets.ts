import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiDelete, apiFetch, apiPut } from "../client";
import type { components } from "../schema";

export type Secret = components["schemas"]["SecretOut"];

const SECRETS_KEY = ["secrets"] as const;

export function useSecrets() {
  return useQuery({
    queryKey: SECRETS_KEY,
    queryFn: () => apiFetch<Secret[]>("/secrets"),
  });
}

export function useSetSecret(name: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (value: string) => apiPut<Secret>(`/secrets/${name}`, { value }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: SECRETS_KEY }),
  });
}

export function useDeleteSecret(name: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiDelete<Secret>(`/secrets/${name}`),
    onSuccess: () => void qc.invalidateQueries({ queryKey: SECRETS_KEY }),
  });
}
