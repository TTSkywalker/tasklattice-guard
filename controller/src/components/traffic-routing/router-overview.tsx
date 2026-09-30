import { useTranslation } from "react-i18next";
import { EndpointProtocolIcon } from "@/components/endpoint-protocol-icon";
import { Link } from "@tanstack/react-router";
import { useLayoutEffect, useRef, useState } from "react";
import { ArrowRight, Cable, GitBranch, History, ShieldCheck } from "lucide-react";
import type { Endpoint } from "@/lib/api";
import type {
  RouterDraft,
  RouterRevision,
  TrafficRouter,
} from "@/lib/traffic-routing-api";
import { Button } from "../ui/button";
import { Badge } from "../ui/badge";
import { StateBadge } from "../product-shell";
import "./router-workspace.scss";
import {
  conditionCount,
  revisionLabel,
  selectorSummary,
} from "./router-view-model";
import { percent } from "./form";

type Names = Array<{ id: string; name: string }>;
export function RouterOverview({
  router,
  endpoints,
  guardrails,
  revisions,
  onRule,
  onEndpoints,
  onRevisions,
  onRouting,
  canEdit,
}: {
  router: TrafficRouter;
  endpoints: Endpoint[];
  guardrails: Names;
  revisions: RouterRevision[];
  canEdit: boolean;
  onRule: (id: string) => void;
  onEndpoints: () => void;
  onRevisions: () => void;
  onRouting: () => void;
}) {
  const { t: localize } = useTranslation();
  const snapshot = router.activeSnapshot;
  const revision = revisions.find((r) => r.revision === router.activeRevision);
  const versions = new Set(
    snapshot?.routes.flatMap((r) =>
      r.targets.map((t) => `${t.guardrailId}:${t.guardrailVersion}`),
    ) ?? [],
  );
  const healthy = endpoints.filter(e => e.runtime_status === "healthy").length;
  const unhealthy = endpoints.filter(e => e.runtime_status === "degraded").length;
  const unknown = endpoints.filter(e => e.enabled && !["healthy", "degraded"].includes(e.runtime_status)).length;
  const disabled = endpoints.filter(e => !e.enabled).length;
  const normalRules = snapshot?.routes.filter(r => r.kind === "normal") ?? [];
  return (
    <div className="router-overview">
      <div className="router-overview-metrics">
        <div><button type="button" className="router-metric-label" onClick={onEndpoints}><Cable aria-hidden="true" />{localize("routing.endpoints2")}<ArrowRight aria-hidden="true" /></button><strong>{endpoints.length}</strong><span className="router-metric-detail">{localize("routing.healthyCount", { count: healthy })}{unhealthy ? localize("routing.needAttentionCount", { count: unhealthy }) : ''}{unknown ? localize("routing.unknownCount", { count: unknown }) : ''}{disabled ? localize("routing.disabledCount", { count: disabled }) : ''}</span></div>
        <div><button type="button" className="router-metric-label" onClick={onRouting}><GitBranch aria-hidden="true" />{localize("routing.publishedRoutingRules")}<ArrowRight aria-hidden="true" /></button><strong>{normalRules.length}</strong><span className="router-metric-detail">{snapshot ? localize("routing.fallbackCount", { count: snapshot.routes.filter(r => r.kind === "fallback").length }) : localize("routing.noPublishedRuleSet")}</span></div>
        <div><span className="router-metric-label"><ShieldCheck aria-hidden="true" />{localize("routing.guardrailVersions")}</span><strong>{versions.size}</strong><span className="router-metric-detail">{snapshot ? localize("routing.pinnedInThePublishedRevision") : localize("routing.assignedWhenARevisionIsPublished")}</span></div>
      </div>
      <div className="router-overview-columns">
        <section className="router-overview-panel router-flow-panel" aria-label={localize("routing.trafficFlow")}>
          <header className="router-panel-heading">
            <div><h2>{localize("routing.trafficFlow")}</h2><p>{snapshot ? localize("routing.flowDescription", { revision: revisionLabel(revision) }) : localize("routing.noRevisionHasBeenPublishedDraftRulesAreNot")}</p></div>
          </header>
          {!endpoints.length && <div className="router-endpoint-notice"><Cable aria-hidden="true" /><p>{localize("routing.noEndpointsAreAttachedToThisRouter")}</p><Button variant="ghost" onClick={onEndpoints}>{canEdit ? localize("routing.attachEndpoint") : localize("routing.viewEndpoints")}</Button></div>}
          {snapshot ? <TrafficFlow snapshot={snapshot} endpoints={endpoints} guardrails={guardrails} onRule={onRule} /> : <div className="router-flow-empty">
            <div className="router-flow-stages" aria-hidden="true"><span><Cable /><span>{localize("routing.endpoint")}</span></span><ArrowRight /><span><GitBranch /><span>{localize("routing.routing")}</span></span><ArrowRight /><span><ShieldCheck /><span>{localize("routing.guardrail")}</span></span></div>
            <h3>{localize("routing.trafficFlowAppearsAfterTheFirstPublication")}</h3>
            <p>{localize("routing.configureRoutingRulesAndChooseGuardrailVersionsThenReview")}</p>
            <Button variant="outline" onClick={onRouting}>{localize("routing.viewRouting")}</Button>
          </div>}
        </section>
        <aside className="router-overview-sidebar">
          <section className="router-overview-panel" aria-label={localize("routing.currentDeployment")}>
            <header className="router-panel-heading"><h2>{localize("routing.currentDeployment")}</h2><StateBadge state={router.rolloutStatus} label={router.rolloutStatus === 'active' ? localize("routing.active") : router.rolloutStatus === 'failed' ? localize("routing.rolloutFailed") : router.rolloutStatus === 'distributing' ? localize("routing.distributing") : localize("routing.unpublished")} /></header>
            {router.activeRevision !== null ? <dl className="router-deployment-facts">
              <div><dt>{localize("routing.revision")}</dt><dd className="font-mono">{revision ? revisionLabel(revision) : `r${router.activeRevision}`}</dd></div>
              <div><dt>{localize("routing.publishedBy")}</dt><dd>{revision?.createdBy ?? '—'}</dd></div>
              <div><dt>{localize("routing.publishedAt")}</dt><dd>{revision ? new Date(revision.createdAt).toLocaleString() : '—'}</dd></div>
            </dl> : <div className="router-panel-empty"><p>{localize("routing.noDeployedRevision")}</p><span>{localize("routing.draftChangesTakeEffectOnlyAfterPublicationAndRunner")}</span></div>}
          </section>
          <section className="router-overview-panel" aria-label={localize("routing.recentRevisions")}>
            <header className="router-panel-heading"><h2><History aria-hidden="true" />{localize("routing.recentRevisions")}</h2><Button variant="link" size="sm" onClick={onRevisions}>{localize("routing.viewAll")}</Button></header>
            {revisions.length ? <ul className="router-revision-list">{revisions.slice(0, 3).map(r => <li key={r.revision}>
              <code>{revisionLabel(r)}</code><span>{r.revision === router.activeRevision ? router.rolloutStatus === 'active' ? localize("routing.active") : router.rolloutStatus === 'failed' ? localize("routing.rolloutFailed") : localize("routing.deploying") : localize("routing.previous")}</span>
            </li>)}</ul> : <div className="router-panel-empty"><p>{localize("routing.noPublishedRevisions")}</p><span>{localize("routing.publicationHistoryWillAppearHere")}</span></div>}
          </section>
        </aside>
      </div>
    </div>
  );
}

export function TrafficFlow({
  snapshot,
  endpoints,
  guardrails,
  onRule,
}: {
  snapshot: RouterDraft;
  endpoints: Endpoint[];
  guardrails: Names;
  onRule: (id: string) => void;
}) {
  const { t: localize } = useTranslation();
  const root = useRef<HTMLDivElement>(null);
  const [lines, setLines] = useState<
    Array<{ d: string; label?: string; x: number; y: number }>
  >([]);
  const normal = snapshot.routes.filter((r) => r.kind === "normal");
  const fallback = snapshot.routes.find((r) => r.kind === "fallback");
  useLayoutEffect(() => {
    const el = root.current;
    if (!el) return;
    const update = () => {
      const bounds = el.getBoundingClientRect();
      const result: typeof lines = [];
      const node = (id: string) =>
        Array.from(el.querySelectorAll<HTMLElement>("[data-flow-node]"))
          .find((n) => n.dataset.flowNode === id)
          ?.getBoundingClientRect();
      const connect = (from: string, to: string, label?: string) => {
        const a = node(from),
          b = node(to);
        if (!a || !b) return;
        const x1 = a.right - bounds.left,
          y1 = a.top + a.height / 2 - bounds.top,
          x2 = b.left - bounds.left,
          y2 = b.top + b.height / 2 - bounds.top;
        const mid = (x1 + x2) / 2;
        result.push({
          d: `M ${x1} ${y1} H ${mid} V ${y2} H ${x2}`,
          label,
          x: x2 - 28,
          y: y2 - 7,
        });
      };
      for (const r of normal) {
        if (r.enabled) connect("sources", r.id);
        for (const t of r.targets) connect(r.id, t.id, percent(t.weightBps));
      }
      if (!normal.length && fallback) connect("sources", "unmatched");
      if (fallback) {
        connect("unmatched", fallback.id);
        for (const t of fallback.targets)
          connect(fallback.id, t.id, percent(t.weightBps));
      }
      setLines(result);
    };
    update();
    const observer = new ResizeObserver(update);
    observer.observe(el);
    el.querySelectorAll("[data-flow-node]").forEach((n) => observer.observe(n));
    return () => observer.disconnect();
  }, [snapshot, endpoints, guardrails]);
  const nodeClass =
    "router-flow-node relative z-10 min-w-0 border bg-card p-4 text-left text-sm";
  return (
    <div
      className="router-traffic-flow overflow-x-auto"
      tabIndex={0}
      aria-label={localize("routing.publishedTrafficFlow")}
    >
      <div
        ref={root}
        className="relative grid min-w-[760px] grid-cols-[minmax(160px,28fr)_minmax(40px,5fr)_minmax(180px,30fr)_minmax(50px,5fr)_minmax(180px,32fr)] gap-y-5 p-5"
      >
        <svg
          className="pointer-events-none absolute inset-0 h-full w-full text-[var(--cds-border-strong-01)]"
          aria-hidden="true"
        >
          {lines.map((l, i) => (
            <g key={i}>
              <path
                d={l.d}
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
              />
              <text
                x={l.x}
                y={l.y}
                textAnchor="middle"
                className="fill-muted-foreground text-xs"
              >
                {l.label}
              </text>
            </g>
          ))}
        </svg>
        <h3 className="col-start-1 text-xs font-medium text-muted-foreground">{localize("routing.endpoints2")}</h3>
        <h3 className="col-start-3 text-xs font-medium text-muted-foreground">{localize("routing.routingRulesFirstMatchWins")}</h3>
        <h3 className="col-start-5 text-xs font-medium text-muted-foreground">{localize("routing.guardRailsPinnedVersions")}</h3>
        <div
          data-flow-node="sources"
          className="col-start-1 space-y-3 self-center"
          style={{ gridRow: `2 / span ${Math.max(normal.length, 1)}` }}
        >
          {endpoints.map((e) => (
            <Link
              key={e.id}
              to="/integration/endpoint"
              search={{ endpointId: e.id }}
              className={`${nodeClass} block hover:border-primary/40`}
            >
              <div className="flex items-center gap-2">
                <EndpointProtocolIcon protocol={e.protocol} size="sm" />
                <span className="line-clamp-2 font-medium" title={e.name}>
                  {e.name}
                </span>
              </div>
              <p className={`mt-2 text-xs ${e.runtime_status === "healthy" ? "text-[var(--success)]" : e.runtime_status === "degraded" ? "text-destructive" : "text-muted-foreground"}`}>
                ●{" "}
                {e.runtime_status === "healthy"
                  ? localize("routing.healthy2")
                  : e.runtime_status === "degraded"
                    ? localize("routing.unhealthy")
                    : e.enabled
                      ? localize("routing.healthUnknown")
                      : localize("routing.disabled")}
              </p>
            </Link>
          ))}
          {!endpoints.length && (
            <p className={`${nodeClass} text-muted-foreground`}>{localize("routing.noAttachedEndpoints2")}</p>
          )}
        </div>
        {normal.map((r, i) => (
          <div key={r.id} className="contents">
            <button
              data-flow-node={r.id}
              style={{ gridRow: i + 2 }}
              className={`${nodeClass} col-start-3 self-center hover:border-primary/40`}
              onClick={() => onRule(r.id)}
            >
              <span className="flex items-center gap-2 font-medium">
                <GitBranch className="size-4" />
                {String(i + 1).padStart(2, "0")} · {r.name}
              </span>
              <span
                title={selectorSummary(r.selector.expression)}
                className="mt-2 line-clamp-2 block text-xs text-muted-foreground"
              >
                {selectorSummary(r.selector.expression)}
              </span>
              <span className="mt-2 block text-xs text-muted-foreground">
                {localize("routing.conditionCount", { count: conditionCount(r.selector.expression) })}{!r.enabled ? ` · ${localize("routing.disabled")}` : ""}
              </span>
            </button>
            <div
              style={{ gridRow: i + 2 }}
              className="col-start-5 space-y-3 self-center"
            >
              {r.targets.map((t) => (
                <a
                  key={t.id}
                  data-flow-node={t.id}
                  href={`/guardrails/${encodeURIComponent(t.guardrailId)}`}
                  className={`${nodeClass} block hover:border-primary/40`}
                >
                  <span className="flex items-start gap-2">
                    <ShieldCheck className="size-4 shrink-0 text-muted-foreground" />
                    <span className="min-w-0 break-words font-medium">
                      {guardrails.find((g) => g.id === t.guardrailId)?.name ??
                        localize("routing.guardRailUnavailable")}
                    </span>
                  </span>
                  <Badge
                    variant="secondary"
                    className="mt-2 max-w-full break-all whitespace-normal"
                  >
                    {t.guardrailVersion || localize("routing.versionUnavailable")}
                  </Badge>
                </a>
              ))}
            </div>
          </div>
        ))}
        {fallback && (
          <div className="contents">
            <div
              data-flow-node="unmatched"
              style={{ gridRow: Math.max(normal.length, 1) + 2 }}
              className={`${nodeClass} col-start-1 self-center border-dashed bg-muted/30`}
            >{localize("routing.unmatchedTraffic")}</div>
            <button
              data-flow-node={fallback.id}
              style={{ gridRow: Math.max(normal.length, 1) + 2 }}
              className={`${nodeClass} col-start-3 self-center border-dashed bg-muted/30`}
              onClick={() => onRule(fallback.id)}
            >
              <span className="font-medium">{localize("routing.fallback")}</span>
              <span className="mt-1 block text-xs text-muted-foreground">{localize("routing.usedWhenNoRoutingRulesMatch")}</span>
            </button>
            <div
              style={{ gridRow: Math.max(normal.length, 1) + 2 }}
              className="col-start-5 space-y-3"
            >
              {fallback.targets.map((t) => (
                <a
                  data-flow-node={t.id}
                  key={t.id}
                  href={`/guardrails/${encodeURIComponent(t.guardrailId)}`}
                  className={`${nodeClass} block border-dashed bg-muted/30`}
                >
                  <span className="flex items-center gap-2">
                    <ShieldCheck className="size-4" />
                    {guardrails.find((g) => g.id === t.guardrailId)?.name ??
                      localize("routing.guardRailUnavailable")}
                  </span>
                  <Badge
                    variant="secondary"
                    className="mt-2 max-w-full break-all whitespace-normal"
                  >
                    {t.guardrailVersion}
                  </Badge>
                </a>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
