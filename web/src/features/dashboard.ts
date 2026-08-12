import { useQuery } from "@tanstack/react-query";

import { queryKeys } from "@/features/query-keys";
import {
  getDecisions,
  getGuardrails,
  getMetrics,
  type MetricWindow,
} from "@/lib/api";

export type DashboardFilters = {
  guardrailId?: string;
  window: MetricWindow;
};

export function useGuardrailsDashboard(filters: DashboardFilters) {
  const metrics = useQuery({
    queryKey: queryKeys.metricsScope(filters),
    queryFn: () => getMetrics(filters),
    refetchInterval: 15_000,
  });
  const decisions = useQuery({
    queryKey: [...queryKeys.decisions, filters],
    queryFn: () => getDecisions({ ...filters, kind: "interaction.decision", limit: 8 }),
    refetchInterval: 15_000,
  });
  const guardrails = useQuery({
    queryKey: queryKeys.guardrails,
    queryFn: getGuardrails,
  });
  return {
    metrics,
    decisions,
    guardrails,
    error: metrics.error ?? decisions.error ?? guardrails.error,
  };
}

export function getMetricInterval(window: MetricWindow) {
  const intervals: Record<MetricWindow, "1m" | "15m" | "1h" | "6h" | "1d"> = {
    "1h": "1m",
    "24h": "15m",
    "7d": "1h",
    "15d": "6h",
    "30d": "1d",
  };
  return intervals[window];
}
