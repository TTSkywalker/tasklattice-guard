import { useEffect, useState } from "react";
import { FileCode2, PackageOpen } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { GuardrailVersionDetail } from "@/lib/api";
import { cn } from "@/lib/utils";

export function CompiledRuntime({ detail }: { detail: GuardrailVersionDetail }) {
  const { t } = useTranslation();
  const [selectedPath, setSelectedPath] = useState(detail.artifacts[0]?.path ?? "");
  const selectedArtifact = detail.artifacts.find((artifact) => artifact.path === selectedPath) ?? detail.artifacts[0];

  useEffect(() => {
    if (!detail.artifacts.some((artifact) => artifact.path === selectedPath)) {
      setSelectedPath(detail.artifacts[0]?.path ?? "");
    }
  }, [detail.artifacts, selectedPath]);

  return (
    <Card className="gap-0 overflow-hidden py-0 shadow-none">
      <Tabs defaultValue="summary" className="gap-0">
        <header className="border-b px-4 pt-4">
          <div className="flex items-start gap-2">
            <PackageOpen className="mt-0.5 size-4 shrink-0 text-primary" />
            <div className="min-w-0">
              <CardTitle>{t("guardrails.compiledRuntime")}</CardTitle>
              <CardDescription className="mt-1">
                {t("guardrails.compiledRuntimeSummary", {
                  rails: detail.rails.length,
                  actions: detail.actions.length,
                  models: detail.models.length,
                  files: detail.artifacts.length,
                })}
              </CardDescription>
            </div>
          </div>
          <TabsList className="mt-2" aria-label={t("guardrails.compiledRuntimeViews")}>
            <TabsTrigger value="summary">{t("guardrails.compiledRuntimeSummaryTab")}</TabsTrigger>
            <TabsTrigger value="files">{t("guardrails.generatedFilesTab", { count: detail.artifacts.length })}</TabsTrigger>
          </TabsList>
        </header>

        <TabsContent value="summary" className="m-0">
          <div className="grid lg:grid-cols-2">
            <RuntimeExecutionSummary detail={detail} />
            <RuntimeDependencySummary detail={detail} />
          </div>
        </TabsContent>

        <TabsContent value="files" className="m-0">
          {selectedArtifact ? (
            <div className="grid min-w-0 lg:grid-cols-[14rem_minmax(0,1fr)]">
              <div className="border-b p-3 lg:border-r lg:border-b-0">
                <div className="lg:hidden">
                  <label className="mb-1.5 block text-xs font-medium text-muted-foreground" htmlFor="compiled-runtime-file">
                    {t("guardrails.generatedFile")}
                  </label>
                  <Select value={selectedArtifact.path} onValueChange={setSelectedPath}>
                    <SelectTrigger id="compiled-runtime-file" className="min-h-11" aria-label={t("guardrails.generatedFile")}>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {detail.artifacts.map((artifact) => <SelectItem key={artifact.path} value={artifact.path}>{artifact.path}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <nav className="hidden space-y-1 lg:block" aria-label={t("guardrails.artifactFiles")}>
                  {detail.artifacts.map((artifact) => (
                    <button
                      key={artifact.path}
                      type="button"
                      className={cn(
                        "flex min-h-11 w-full items-center gap-2 rounded-md px-3 text-left font-mono text-xs transition-colors focus-visible:outline-2 focus-visible:outline-ring",
                        artifact.path === selectedArtifact.path
                          ? "bg-primary/[0.08] text-primary"
                          : "text-muted-foreground hover:bg-muted hover:text-foreground",
                      )}
                      aria-current={artifact.path === selectedArtifact.path ? "true" : undefined}
                      onClick={() => setSelectedPath(artifact.path)}
                    >
                      <FileCode2 className="size-3.5 shrink-0" />
                      <span className="min-w-0 truncate">{artifact.path}</span>
                    </button>
                  ))}
                </nav>
              </div>
              <section className="min-w-0" aria-label={selectedArtifact.path}>
                <header className="flex min-h-11 items-center justify-between gap-3 border-b bg-muted/20 px-4 py-2">
                  <code className="truncate text-xs font-medium">{selectedArtifact.path}</code>
                  <Badge variant="outline" className="shrink-0 uppercase">{selectedArtifact.language}</Badge>
                </header>
                <pre className="max-h-[32rem] overflow-auto bg-muted/10 p-4 font-mono text-xs leading-5 whitespace-pre"><code>{selectedArtifact.content}</code></pre>
              </section>
            </div>
          ) : (
            <p className="px-4 py-10 text-center text-sm text-muted-foreground">{t("guardrails.noGeneratedFiles")}</p>
          )}
        </TabsContent>
      </Tabs>
    </Card>
  );
}

function RuntimeExecutionSummary({ detail }: { detail: GuardrailVersionDetail }) {
  const { t } = useTranslation();
  return (
    <section className="min-w-0 border-b p-4 lg:border-r lg:border-b-0" aria-labelledby="compiled-runtime-execution">
      <h3 id="compiled-runtime-execution" className="text-sm font-semibold">{t("guardrails.compiledRailsActions")}</h3>
      {detail.rails.length || detail.actions.length ? (
        <div className="mt-3 divide-y rounded-lg border">
          {detail.rails.map((rail, index) => (
            <div key={`${rail.rail_type}:${rail.flow}:${index}`} className="flex min-h-11 items-center justify-between gap-3 px-3 py-2">
              <code className="min-w-0 truncate text-xs">{rail.flow}</code>
              <Badge variant="outline" className="shrink-0 uppercase">{rail.rail_type}</Badge>
            </div>
          ))}
          {detail.actions.map((action) => (
            <div key={`${action.name}:${action.flow}`} className="grid min-h-11 gap-1 px-3 py-2 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
              <div className="min-w-0">
                <code className="block truncate text-xs">{action.name}{action.version ? `@${action.version}` : ""}</code>
                {action.phases.length ? <span className="mt-0.5 block text-[11px] uppercase text-muted-foreground">{action.phases.join(" · ")}</span> : null}
              </div>
              <span className="text-xs tabular-nums text-muted-foreground">{action.timeout_ms} ms</span>
            </div>
          ))}
        </div>
      ) : <p className="mt-3 text-xs text-muted-foreground">{t("guardrails.noCompiledRailsActions")}</p>}
    </section>
  );
}

function RuntimeDependencySummary({ detail }: { detail: GuardrailVersionDetail }) {
  const { t } = useTranslation();
  return (
    <section className="min-w-0 p-4" aria-labelledby="compiled-runtime-dependencies">
      <h3 id="compiled-runtime-dependencies" className="text-sm font-semibold">{t("guardrails.dependenciesModels")}</h3>
      {detail.models.length || detail.dependencies.length ? (
        <div className="mt-3 space-y-4">
          {detail.models.length ? <RuntimeReferenceList label={t("guardrails.models")} items={detail.models.map((model) => `model:${model}`)} /> : null}
          {detail.dependencies.length ? <RuntimeReferenceList label={t("guardrails.dependencies")} items={detail.dependencies.map((item) => `${item.kind}:${item.name}@${item.version}`)} /> : null}
        </div>
      ) : <p className="mt-3 text-xs text-muted-foreground">{t("guardrails.noExternalDependencies")}</p>}
    </section>
  );
}

function RuntimeReferenceList({ label, items }: { label: string; items: string[] }) {
  return (
    <div>
      <h4 className="text-xs font-medium text-muted-foreground">{label}</h4>
      <div className="mt-1.5 divide-y rounded-lg border">
        {items.map((item) => <code key={item} className="block min-w-0 truncate px-3 py-2.5 text-xs" title={item}>{item}</code>)}
      </div>
    </div>
  );
}
