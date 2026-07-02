import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiPost } from "../client";
import { queryKeys } from "../queryKeys";

type GateDecision = { decision: "approve" | "reject" };

export function useResolveGate(runId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: GateDecision) => apiPost(`/runs/${runId}/gate`, vars),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.run(runId) });
      void qc.invalidateQueries({ queryKey: queryKeys.runEvents(runId) });
    },
  });
}
