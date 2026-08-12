import { useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import type { PlaygroundTurn } from "@/components/playground/types";
import { queryKeys } from "@/features/query-keys";

export function usePlaygroundSession(guardrailId: string) {
  const queryClient = useQueryClient();
  const queryKey = queryKeys.playgroundSession(guardrailId);
  const session = useQuery({
    queryKey,
    queryFn: async () => [] as PlaygroundTurn[],
    initialData: [] as PlaygroundTurn[],
    staleTime: Infinity,
    gcTime: Infinity,
  });

  const appendTurn = useCallback((turn: PlaygroundTurn) => {
    queryClient.setQueryData<PlaygroundTurn[]>(queryKey, (current = []) => [...current, turn]);
  }, [queryClient, queryKey]);

  const clearTurns = useCallback(() => {
    queryClient.setQueryData<PlaygroundTurn[]>(queryKey, []);
  }, [queryClient, queryKey]);

  return { turns: session.data, appendTurn, clearTurns };
}
