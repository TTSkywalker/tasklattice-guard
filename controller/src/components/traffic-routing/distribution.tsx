import { Activity, AlertTriangle, CheckCircle2, GitBranch, RefreshCw } from 'lucide-react';
import { Table, TableHead, TableBody, TableRow, TableHeader, TableCell } from '@/components/ui/table';
import './router-monitoring.scss';
import { revisionLabel } from "./router-view-model";
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from '@tanstack/react-router';
import { getRouterDistribution, getRouterRevisions, type TrafficRouter, type DistributionReport, type RouterDraft, type DistributionRow } from '@/lib/traffic-routing-api';
import { listControllerGuardrails } from '@/lib/controller-api';
import { EntitySheet } from '@/components/entity-sheet';
import { EmptyState, ErrorNotice } from '@/components/product-shell';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Field, NativeSelect, share, percent, useRoutingText } from './form';
export function DistributionOverview({ router, endpoints }: { router: TrafficRouter; endpoints: Array<{ id: string; name: string }> }) {
  const t = useRoutingText();
  const [hours, setHours] = useState(24);
  const [revision, setRevision] = useState('');
  const [endpoint, setEndpoint] = useState('');
  const [routeId, setRouteId] = useState<string | null>(null);
  const query = useQuery({ queryKey: ['traffic-routers', router.id, 'distribution', hours, revision, endpoint], queryFn: () => getRouterDistribution(router.id, hours, revision ? Number(revision) : undefined, endpoint || undefined), refetchInterval: 30000 });
  const history = useQuery({ queryKey: ['traffic-routers', router.id, 'revisions'], queryFn: () => getRouterRevisions(router.id) });
  const guardrails = useQuery({ queryKey: ['routing-guardrails'], queryFn: listControllerGuardrails });
  const name = (id: string) => guardrails.data?.items.find(g => g.id === id)?.name ?? id;
  const report = query.data;
  const snapshots = report?.revisions ?? history.data?.items ?? [];
  const observedRevision = [...new Set(report?.rows.map(row => row.routerRevision).filter(Boolean))];
  const snapshot = revision ? snapshots.find(r => r.revision === Number(revision))?.snapshot : observedRevision.length === 1 ? snapshots.find(r => r.revision === observedRevision[0])?.snapshot : router.activeSnapshot;
  const routeIds = [...new Set([...(snapshot?.routes.map(r => r.id) ?? []), ...(report?.rows.flatMap(r => r.routeId ? [r.routeId] : []) ?? [])])];
  const routeName = (id: string) => snapshot?.routes.find(r => r.id === id)?.name ?? history.data?.items.flatMap(r => r.snapshot.routes).find(r => r.id === id)?.name ?? id;
  const fallbackIds = new Set([...(snapshot?.routes.filter(r => r.kind === 'fallback').map(r => r.id) ?? []), ...(history.data?.items.flatMap(r => r.snapshot.routes.filter(route => route.kind === 'fallback').map(route => route.id)) ?? [])]);
  const fallback = report?.rows.filter(r => r.routeId !== null && fallbackIds.has(r.routeId)).reduce((n, r) => n + r.count, 0) ?? 0;
  const assigned = report?.assigned ?? report?.rows.filter(isAssigned).reduce((n, r) => n + r.count, 0) ?? 0;
  const errors = report?.rows.filter(isAssigned).reduce((n, r) => n + r.errors, 0) ?? 0;
  const completed = report?.rows.filter(isAssigned).reduce((n, r) => n + r.completed, 0) ?? 0;
  const metrics = [
    { label: t('总调用', 'Total calls'), value: report?.total.toLocaleString(), detail: t('逻辑调用首次路由决策', 'First routing decisions'), tone: '' },
    { label: t('已分配', 'Assigned'), value: assigned.toLocaleString(), detail: t('已选定目标', 'Target selected'), tone: '' },
    { label: t('未分配', 'Unassigned'), value: report?.unassigned?.toLocaleString() ?? '—', detail: t('未选定目标', 'No target selected'), tone: (report?.unassigned ?? 0) > 0 ? 'warning' : '' },
    { label: 'Fallback', value: share(fallback, report?.total ?? 0), detail: t(`${fallback.toLocaleString()} 次调用`, `${fallback.toLocaleString()} calls`), tone: '' },
    { label: t('执行错误率', 'Execution error rate'), value: share(errors, completed), detail: t(`${errors.toLocaleString()} 次错误 / ${completed.toLocaleString()} 次已完成`, `${errors.toLocaleString()} errors / ${completed.toLocaleString()} completed`), tone: errors > 0 ? 'error' : '' },
  ];
  const maxTrend = Math.max(...(report?.trend?.map(point => point.count) ?? []), 1);
  return <div className="router-monitoring">
    <section className="monitoring-query" aria-label={t('监控筛选', 'Monitoring filters')}>
      <div className="monitoring-toolbar">
        <Field label={t('时间窗口', 'Time window')}><NativeSelect value={hours} onChange={e => setHours(Number(e.target.value))}>{[[0.25, '15m'], [1, '1h'], [24, '24h'], [168, '7d']].map(([v, label]) => <option key={v} value={v}>{label}</option>)}</NativeSelect></Field>
        <Field label={t('版本', 'Revision')}><NativeSelect value={revision} onChange={e => setRevision(e.target.value)}><option value="">{t('全部版本', 'All revisions')}</option>{history.data?.items.map(r => <option key={r.revision} value={r.revision}>{revisionLabel(r)}</option>)}</NativeSelect></Field>
        <Field label="Endpoint"><NativeSelect value={endpoint} onChange={e => setEndpoint(e.target.value)}><option value="">{t('全部接入', 'All Endpoints')}</option>{endpoints.filter(e => router.endpointIds.includes(e.id)).map(e => <option key={e.id} value={e.id}>{e.name}</option>)}</NativeSelect></Field>
        <Button variant="ghost" disabled={query.isFetching} onClick={() => void query.refetch()}><RefreshCw aria-hidden="true" />{t('刷新', 'Refresh')}</Button>
      </div>
      {report && <div className="monitoring-freshness">
        <span className={report.telemetryFresh ? 'monitoring-current' : 'monitoring-delayed'}>{report.telemetryFresh ? <CheckCircle2 aria-hidden="true" /> : <AlertTriangle aria-hidden="true" />}{report.telemetryFresh ? t('遥测已更新', 'Telemetry current') : t('遥测延迟', 'Telemetry delayed')}</span>
        <span>{t('数据水位', 'Data watermark')}: {report.dataWatermark ? new Date(report.dataWatermark).toLocaleString() : t('尚无数据', 'No data')} · {report.completeness}</span>
      </div>}
    </section>
    {history.error && <ErrorNotice error={history.error} />}
    {query.isPending && <Skeleton className="h-44" />}
    {query.error && <div className="monitoring-panel p-5 space-y-3"><ErrorNotice error={query.error} /><Button variant="outline" onClick={() => void query.refetch()}>{t('重试统计', 'Retry metrics')}</Button></div>}
    {report && <>
      {!report.telemetryFresh && <p role="alert" className="monitoring-notice monitoring-notice-warning"><AlertTriangle aria-hidden="true" />{t('遥测延迟或不可用；数字可能不完整。', 'Telemetry is delayed or unavailable; counts may be incomplete.')}</p>}
      {report.multipleRevisions && <p role="status" className="monitoring-notice"><GitBranch aria-hidden="true" />{t('窗口包含多个配置版本；请选择 revision 后比较配置占比。', 'This window contains multiple revisions. Select a revision to compare configured shares.')}</p>}
      <dl className="monitoring-metrics">{metrics.map(metric => <div key={metric.label} data-tone={metric.tone}>
        <dt>{metric.label}</dt><dd>{metric.value}</dd><dd className="monitoring-metric-detail">{metric.detail}</dd>
      </div>)}</dl>
      <section className="monitoring-panel" aria-label={t('Route 流量分布', 'Route distribution')}>
        <header className="monitoring-panel-heading"><div><h3><GitBranch aria-hidden="true" />{t('Route 流量分布', 'Route distribution')}</h3><p>{t('每条 Route 占 Router 调用量的比例；目标占比以该 Route 的已分配量为分母。', 'Route share uses all Router calls. Target shares use assignments within each Route.')}</p></div></header>
        {!report.total && report.telemetryFresh ? <div className="monitoring-empty"><EmptyState title={t('暂无流量', 'No traffic yet')} description={t('有新逻辑调用后显示实际分布。草稿权重不会替代运行数据。', 'Actual distribution appears after new logical calls. Draft weights never replace runtime data.')} /></div> : !routeIds.length ? <div className="monitoring-empty"><EmptyState title={t('暂无 Route 分配记录', 'No Route assignments available')} description={t('未分配的调用计入上方摘要，不会归入某条 Route。', 'Unassigned calls are included in the summary and are not attributed to a Route.')} /></div> : <Table className="monitoring-route-table" aria-label={t('Route 流量分布', 'Route distribution')}><TableHeader><TableRow>
          {['Route', t('调用量', 'Calls'), t('占 Router 流量', 'Router share'), t('目标实际分布', 'Actual target distribution')].map(label => <TableHead key={label}>{label}</TableHead>)}
        </TableRow></TableHeader><TableBody>{routeIds.map(id => {
          const rows = report.rows.filter(r => r.routeId === id), count = rows.reduce((n, r) => n + r.count, 0);
          const assignedRows = rows.filter(isAssigned);
          const routeAssigned = assignedRows.reduce((n, row) => n + row.count, 0);
          const targets = [...new Set(assignedRows.map(r => `${r.guardrailId}@${r.guardrailVersion}`))];
          return <TableRow key={id}>
            <TableCell><button type="button" className="monitoring-link" onClick={() => setRouteId(id)}>{routeName(id)}</button></TableCell>
            <TableCell><button type="button" className="monitoring-link tabular-nums" onClick={() => setRouteId(id)}>{count.toLocaleString()}</button></TableCell>
            <TableCell className="tabular-nums">{share(count, report.total)}</TableCell>
            <TableCell><button type="button" className="monitoring-targets" onClick={() => setRouteId(id)} aria-label={t(`查看 ${routeName(id)} 的目标分布`, `View targets for ${routeName(id)}`)}>{targets.map(target => {
              const matching = assignedRows.filter(r => `${r.guardrailId}@${r.guardrailVersion}` === target);
              return <span key={target} className="monitoring-target"><span>{name(matching[0]!.guardrailId)}<code>{matching[0]!.guardrailVersion}</code></span><span>{share(matching.reduce((n, r) => n + r.count, 0), routeAssigned)}</span></span>;
            })}{!targets.length && t('查看目标', 'View targets')}</button></TableCell>
          </TableRow>;
        })}</TableBody></Table>}
      </section>
      <section className="monitoring-panel" aria-label={t('Route 调用趋势', 'Calls by Route over time')}>
        <header className="monitoring-panel-heading"><h3><Activity aria-hidden="true" />{t('Route 调用趋势', 'Calls by Route over time')}</h3></header>
        {report.trend?.length ? <div className="monitoring-trend">{report.trend.map((point, index) => <div key={index} className="monitoring-trend-row"><span><time dateTime={point.at}>{new Date(point.at).toLocaleString()}</time><span>{point.routeId ? routeName(point.routeId) : t('未分配', 'Unassigned')}</span></span><meter aria-label={`${point.at} · ${point.routeId ? routeName(point.routeId) : t('未分配', 'Unassigned')}`} min={0} max={maxTrend} value={point.count} /><span>{point.count.toLocaleString()}</span></div>)}</div> : <p className="monitoring-trend-empty">{t('趋势数据暂不可用', 'Trend data unavailable')}</p>}
      </section>
    </>}
    {routeId && report && <TargetDistribution routerId={router.id} routeId={routeId} routeName={routeName(routeId)} report={report} snapshot={snapshot ?? null} name={name} revisionName={n => revisionLabel(history.data?.items.find(r => r.revision === n))} close={() => setRouteId(null)} />}
  </div>;
}

function TargetDistribution({ routerId, routeId, routeName, report, snapshot, name, revisionName, close }: { routerId: string; routeId: string; routeName: string; report: DistributionReport; snapshot: RouterDraft | null; name: (id: string) => string; revisionName: (revision: number) => string; close: () => void }) {
  const t = useRoutingText();
  const rows = report.rows.filter(isAssigned).filter(r => r.routeId === routeId);
  const count = rows.reduce((n, r) => n + r.count, 0);
  return <EntitySheet open onOpenChange={open => { if (!open) close(); }} width="xl" eyebrow="Distribution" title={routeName} description={t('实际占比以此 Route 的已分配量为分母；执行结果以已完成量为分母。', 'Actual share uses this Route’s assignments; outcomes use completed calls.')} footer={<Button onClick={close}>{t('关闭', 'Close')}</Button>}><div className="space-y-4">{!rows.length && <p>{t('此窗口暂无目标分配。', 'No target assignments in this window.')}</p>}{rows.map(row => {
    const configured = !report.multipleRevisions ? snapshot?.routes.find(r => r.id === routeId)?.targets.find(target => target.id === row.targetId && target.guardrailId === row.guardrailId && target.guardrailVersion === row.guardrailVersion)?.weightBps : undefined;
    return <article key={`${row.routerRevision}:${row.targetId}`} className="monitoring-target-detail"><h3 className="font-semibold">{name(row.guardrailId)} · {row.guardrailVersion} <span className="text-sm font-normal">{revisionName(row.routerRevision)}</span></h3><dl className="monitoring-target-metrics">{[[t('配置占比', 'Configured'), configured === undefined ? '—' : percent(configured)], [t('实际占比', 'Actual'), share(row.count, count)], [t('分配量', 'Assignments'), row.count], ['allow / block', `${row.allowed} / ${row.blocked}`], ['transform / intervene', `${row.transformed} / ${row.intervened}`], [t('执行错误率', 'Error rate'), share(row.errors, row.completed)], [t('已完成 / 分配', 'Completed / assigned'), `${row.completed} / ${row.count}`], [t('推断完成（超时）', 'Inferred completions (timeout)'), row.inferredCompletions], [t('端到端 p95（包含等待）', 'End-to-end p95 (includes waiting)'), row.p95Ms === null ? '—' : `${Number(row.p95Ms).toFixed(1)} ms`]].map(([label, value]) => <div key={String(label)}><dt className="text-xs text-muted-foreground">{label}</dt><dd className="mt-1 tabular-nums">{value}</dd></div>)}</dl><Button asChild className="min-h-11" variant="outline"><Link to="/logs" search={{ routerId, routeId, targetId: row.targetId, routerRevision: row.routerRevision, since: report.since, until: report.until }}>{t('查看调用日志', 'View call logs')}</Link></Button></article>;
  })}</div></EntitySheet>;
}

export function isAssigned(row: DistributionRow): row is DistributionRow & { routeId: string; targetId: string; routerRevision: number; guardrailId: string; guardrailVersion: string } {
  return row.assignmentStatus === 'assigned' && Boolean(row.routeId && row.targetId && row.routerRevision && row.guardrailId && row.guardrailVersion);
}
