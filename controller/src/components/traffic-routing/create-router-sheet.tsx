import i18n from "@/i18n";
import { useTranslation } from "react-i18next";
import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { EntitySheet } from '@/components/entity-sheet';
import { ErrorNotice } from '@/components/product-shell';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { MultiSelectCombobox } from '@/components/ui/multi-select-combobox';
import { listControllerEndpoints } from '@/lib/controller-api';
import { createTrafficRouter, getSelectorFields, listTrafficRouters, trafficRouterKeys, type TrafficRoute } from '@/lib/traffic-routing-api';
import { routingIssues } from '../../../shared/traffic-routing';
import { Field } from './form';
import { SelectorEditor } from './selector-editor';
import { TargetsEditor } from './targets-editor';

const newRoute = (kind: TrafficRoute['kind']): TrafficRoute => ({
  id: crypto.randomUUID(), name: kind === 'fallback' ? i18n.t("routing.fallback") : i18n.t("routing.route"), kind, enabled: true,
  selector: { expression: { combinator: 'and', conditions: [] } }, targets: [],
});

export function CreateRouterSheet({ open, onOpenChange, onCreated }: {
  open: boolean; onOpenChange: (open: boolean) => void; onCreated: () => void;
}) {
  const { t: localize } = useTranslation();
  const { t } = useTranslation();
  const client = useQueryClient();
  const [name, setName] = useState('');
  const [endpointIds, setEndpointIds] = useState<string[]>([]);
  const [routes, setRoutes] = useState(() => [newRoute('normal')]);
  const [fallback, setFallback] = useState(() => newRoute('fallback'));
  const endpoints = useQuery({ queryKey: ['routing-source-endpoints'], queryFn: listControllerEndpoints, enabled: open });
  const routers = useQuery({ queryKey: trafficRouterKeys.all, queryFn: listTrafficRouters, enabled: open });
  const fields = useQuery({ queryKey: ['routing-fields', endpointIds], queryFn: () => getSelectorFields(endpointIds), enabled: open && endpointIds.length > 0 });
  const draft = { routes: [...routes, fallback] };
  const issues = routingIssues(draft, true);
  const mutation = useMutation({
    mutationFn: () => createTrafficRouter({ name: name.trim(), endpointIds, draft }),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: trafficRouterKeys.all });
      onCreated();
    },
  });
  const options = (endpoints.data?.items ?? []).map(endpoint => {
    const owner = routers.data?.items.find(router => router.endpointIds.includes(endpoint.id));
    return { value: endpoint.id, label: endpoint.name, meta: endpoint.adapter, disabled: Boolean(owner),
      description: owner ? t("routing.boundTo") + ' ' + owner.name : undefined };
  });
  const updateRoute = (next: TrafficRoute) => setRoutes(current => current.map(route => route.id === next.id ? next : route));

  return <EntitySheet width="xl" open={open} closeDisabled={mutation.isPending} onOpenChange={onOpenChange}
    eyebrow={localize("routing.router")} title={t("routing.createRouter")}
    description={t("routing.selectIncomingTrafficAndRouteItToGuardrails")}
    footer={<><Button variant="outline" disabled={mutation.isPending} onClick={() => onOpenChange(false)}>{t("routing.cancel")}</Button>
      <Button variant="create" disabled={!name.trim() || !endpointIds.length || issues.length > 0 || mutation.isPending || !routers.data || !endpoints.data}
        onClick={() => mutation.mutate()}>{mutation.isPending ? t("routing.creating") : t("routing.createRouter")}</Button></>}>
    <div className="space-y-6">
      <Field label={t("routing.routerName")}><Input autoFocus value={name} onChange={event => setName(event.target.value)} /></Field>
      <div className="space-y-2">
        <h3 className="text-sm font-medium">{t("routing.sourceEndpoints")}</h3>
        <MultiSelectCombobox ariaLabel={t("routing.sourceEndpoints")} options={options} value={endpointIds}
          onValueChange={setEndpointIds} disabled={endpoints.isPending || routers.isPending}
          placeholder={t("routing.searchOrSelectEndpoints")} />
        <p className="text-xs text-muted-foreground">{t("routing.selectedEndpointsShareTheseRulesEachEndpointBelongsTo")}</p>
        {endpoints.error && <ErrorNotice error={endpoints.error} />}{routers.error && <ErrorNotice error={routers.error} />}
      </div>
      <section className="space-y-4">
        <h3 className="font-medium">{t("routing.routeSettings")}</h3>
        {fields.error && <ErrorNotice error={fields.error} />}
        {routes.map((route, index) => <div key={route.id} className="space-y-4 rounded-lg border bg-card p-4">
          <div className="flex items-center justify-between"><h4 className="text-sm font-medium">{localize("routing.route")}{index + 1}</h4>
            <Button variant="destructive" onClick={() => setRoutes(current => current.filter(item => item.id !== route.id))}>{t("routing.removeRoute")}</Button></div>
          <SelectorEditor value={route.selector.expression} fields={fields.data?.items}
            onChange={expression => updateRoute({ ...route, selector: { expression } })} />
          <div className="space-y-2 border-t pt-4"><h4 className="text-sm font-medium">{t("routing.forwardTo")}</h4>
            <TargetsEditor value={route.targets} onChange={targets => updateRoute({ ...route, targets })} /></div>
        </div>)}
        <Button variant="create" disabled={routes.length >= 127} onClick={() => setRoutes(current => [...current, { ...newRoute('normal'), name: `Route ${current.length + 1}` }])}>{t("routing.addRoute")}</Button>
      </section>
      <section className="space-y-3 rounded-lg border bg-card p-4">
        <h3 className="text-sm font-medium">{t("routing.unmatchedTraffic")}</h3>
        <p className="text-xs text-muted-foreground">{t("routing.trafficThatMatchesNoneOfTheRulesIsForwarded")}</p>
        <TargetsEditor value={fallback.targets} onChange={targets => setFallback(current => ({ ...current, targets }))} />
      </section>
      {issues.length > 0 && <p className="text-xs text-muted-foreground">{t("routing.completeTheConditionsAndGuardrailsForEachRuleDistribution")}</p>}
      {mutation.error && <ErrorNotice error={mutation.error} />}
    </div>
  </EntitySheet>;
}
