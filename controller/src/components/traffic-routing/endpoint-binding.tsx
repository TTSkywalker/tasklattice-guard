import { useTranslation } from "react-i18next";
import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Link } from '@tanstack/react-router';
import { listTrafficRouters, trafficRouterKeys } from '@/lib/traffic-routing-api';
import { requestController } from '@/lib/controller-api';
import { useAuth } from '@/lib/auth';
import { ErrorNotice } from '@/components/product-shell';
import { Button } from '@/components/ui/button';
import { Field, NativeSelect } from './form';
export function EndpointRouterBinding({ endpointId }: { endpointId: string }) {
  const { t: localize } = useTranslation();
  const { t } = useTranslation();
  const client = useQueryClient();
  const auth = useAuth();
  const query = useQuery({ queryKey: trafficRouterKeys.all, queryFn: listTrafficRouters });
  const current = query.data?.items.find(router => router.endpointIds.includes(endpointId));
  const [choice, setChoice] = useState<string | null>(null);
  const mutation = useMutation({ mutationFn: () => requestController(`/api/v1/endpoints/${encodeURIComponent(endpointId)}`, { method: 'PATCH', body: JSON.stringify({ routerId: choice || null }) }), onSuccess: async () => { setChoice(null); await client.invalidateQueries({ queryKey: trafficRouterKeys.all }); await client.invalidateQueries({ queryKey: ['controller'] }); } });
  return <section className="space-y-3 rounded-md border p-4"><h3 className="font-semibold">{localize("routing.router")}</h3>{current ? <Link className="inline-flex min-h-11 items-center text-primary" to="/integration/routers/$routerId" params={{ routerId: current.id }}>{current.name} · r{current.activeRevision}</Link> : <p>{t("routing.noRouterIsBoundEvaluationCallsAreUnavailable")}</p>}{query.error && <><ErrorNotice error={query.error} /><Button onClick={() => void query.refetch()}>{localize("routing.retry")}</Button></>}{auth.user?.role === 'admin' && <><Field label={t("routing.publishedRouter")}><NativeSelect disabled={mutation.isPending || !query.data} value={choice ?? current?.id ?? ''} onChange={e => setChoice(e.target.value)}><option value="">{t("routing.unbindDisableEndpointFirst")}</option>{query.data?.items.filter(router => router.activeRevision).map(router => <option key={router.id} value={router.id}>{router.name} · r{router.activeRevision}</option>)}</NativeSelect></Field><p className="text-xs text-muted-foreground">{t("routing.bindingTakesEffectImmediatelyPublishingASharedRouterAffects")}</p><Button disabled={choice === null || mutation.isPending} onClick={() => mutation.mutate()}>{t("routing.saveBinding")}</Button>{mutation.error && <ErrorNotice error={mutation.error} />}</>}</section>;
}
