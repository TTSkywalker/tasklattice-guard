import { TriangleAlert } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import type { Metrics } from "@/lib/api";

export type RuntimeHealthAlertMetrics = {
  system_status: Metrics["system_status"];
  latency_slo: Pick<Metrics["latency_slo"], "p95_status">;
  fail_closed_count: number;
  degraded_integrations: number;
};

export function RuntimeHealthAlert({ metrics }: { metrics: RuntimeHealthAlertMetrics }) {
  const { t } = useTranslation();
  const detailKey = runtimeHealthDetailKey(metrics);

  if (!detailKey) return null;

  return (
    <Alert className="border-amber-200 bg-amber-50/70 text-amber-950">
      <TriangleAlert />
      <AlertTitle>{t("dashboard.degraded")}</AlertTitle>
      <AlertDescription className="text-amber-900/75">{t(detailKey, { count: metrics.degraded_integrations })}</AlertDescription>
    </Alert>
  );
}

function runtimeHealthDetailKey(metrics: RuntimeHealthAlertMetrics) {
  if (metrics.fail_closed_count > 0) return "dashboard.healthFailClosed";
  if (metrics.latency_slo.p95_status === "breached") return "dashboard.healthLatency";
  if (metrics.degraded_integrations > 0) return "dashboard.healthIntegration";
  if (metrics.system_status === "degraded") return "dashboard.healthSystem";
  return null;
}
