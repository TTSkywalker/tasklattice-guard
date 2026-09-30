import { useTranslation } from "react-i18next";
import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { ErrorNotice } from '@/components/product-shell';
import { Field } from './form';
import { testTrafficSelector, type RouterDraft } from '@/lib/traffic-routing-api';
import { routingInputSchema } from '../../../shared/traffic-routing';
export function SelectorPreviewPanel({ routerId, draft, endpointIds }: { routerId: string; draft: RouterDraft; endpointIds: string[] }) {
  const { t } = useTranslation();
  const [sample, setSample] = useState(() => JSON.stringify({ endpointId: endpointIds[0] ?? 'simulated-endpoint', fields: {}, business_request: { 'x-channel': ['partner'] }, endpoint_request: {} }, null, 2));
  const mutation = useMutation({ mutationFn: () => testTrafficSelector(routerId, draft, routingInputSchema.parse(JSON.parse(sample))) });
  return <section className="space-y-3 border-t pt-5"><h3 className="font-semibold">{t("routing.testSelectorAndRouterOrder")}</h3><p className="text-sm text-muted-foreground">{endpointIds.length ? t("routing.redactedSampleMatchOnlyNoGuardrailExecutionOrStatistics") : t("routing.simulatedInputNoEndpointIsBoundPublishAndBinding")}</p>
    <Field label={t("routing.requestSampleJSONThisPreviewOnly")}><Textarea className="field:min-h-48 field:font-mono field:text-xs" value={sample} onChange={e => { setSample(e.target.value); mutation.reset(); }} /></Field>
    <p className="text-xs text-muted-foreground">{t("routing.headersUseValueArraysCredentialHeadersAreExcludedHTTP")}</p>
    <Button className="min-h-11" disabled={mutation.isPending} onClick={() => mutation.mutate()}>{mutation.isPending ? t("routing.testing") : t("routing.testSelector")}</Button>
    {mutation.error && <ErrorNotice error={mutation.error} />}
    {mutation.data && <div aria-live="polite" className="space-y-2">{mutation.data.items.map(row => <article key={row.routeId} className="rounded-md border p-3 text-sm"><strong>{draft.routes.find(r => r.id === row.routeId)?.name ?? row.routeId}</strong><p>{t("routing.independentMatch")}: {String(row.independentMatch)} · {row.received ? t("routing.receivedByThisRoute") : row.state === 'not_evaluated' ? t("routing.notEvaluatedInOrder") : row.state === 'not_applicable' ? t("routing.notApplicable") : t("routing.notMatched")}</p>{row.blockedBy && <p>{t("routing.receivedEarlierBy")}: {draft.routes.find(r => r.id === row.blockedBy)?.name ?? row.blockedBy}</p>}<details className="mt-2"><summary className="min-h-11 cursor-pointer py-2">{t("routing.conditionResultsAndReasons")}</summary><pre className="overflow-auto whitespace-pre-wrap break-all text-xs">{JSON.stringify(row.children, null, 2)}</pre></details></article>)}<details><summary className="min-h-11 cursor-pointer py-2">{t("routing.normalizedInput")}</summary><pre className="overflow-auto whitespace-pre-wrap break-all text-xs">{JSON.stringify(mutation.data.normalizedInput ?? {}, null, 2)}</pre></details></div>}
  </section>;
}
