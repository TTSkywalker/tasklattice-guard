import { useMemo, useState } from "react";
import { Link } from "@tanstack/react-router";
import {
  ArrowRight,
  BookOpen,
  CheckCircle2,
  CircleHelp,
  Code2,
  Network,
  Search,
  ShieldCheck,
  UserRound,
  Wrench,
} from "lucide-react";
import { useTranslation } from "react-i18next";

import { PageHeader } from "@/components/product-shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  getHelpContent,
  searchHelpContent,
  type GlossaryEntry,
  type HelpArticle,
  type HelpContent,
  type HelpGuide,
} from "@/features/help-content";
import { cn } from "@/lib/utils";

const ROLE_ICONS = { user: UserRound, developer: Code2, operator: Wrench } as const;

export function HelpPage() {
  const { i18n } = useTranslation();
  const locale = i18n.language.toLowerCase().startsWith("zh") ? "zh-CN" : "en";
  const content = useMemo(() => getHelpContent(locale), [locale]);
  const [query, setQuery] = useState("");
  const searching = Boolean(query.trim());
  const results = useMemo(() => searchHelpContent(content, query), [content, query]);
  const resultCount = results.guides.reduce((total, item) => total + item.articles.length, 0) + results.glossary.length;

  return (
    <section className="py-6 sm:py-8">
      <PageHeader title={content.title} description={content.description} />

      <div className="mt-6 overflow-hidden rounded-xl border bg-card shadow-[var(--shadow-surface)]">
        <div className="grid gap-5 p-5 sm:p-6 lg:grid-cols-[minmax(0,1fr)_18rem] lg:items-end">
          <div className="min-w-0">
            <div className="flex items-center gap-3">
              <span className="grid size-10 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary"><BookOpen className="size-5" /></span>
              <div><h2 className="text-base font-semibold">{content.searchLabel}</h2><p className="mt-0.5 text-xs leading-5 text-muted-foreground">{content.searchHint}</p></div>
            </div>
            <label className="relative mt-4 block max-w-3xl">
              <span className="sr-only">{content.searchLabel}</span>
              <Search className="pointer-events-none absolute top-1/2 left-3.5 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input value={query} onChange={(event) => setQuery(event.target.value)} className="min-h-12 bg-background pl-10 pr-24" placeholder={content.searchPlaceholder} />
              {searching ? <Button type="button" variant="ghost" size="sm" className="absolute top-1/2 right-1 min-h-11 -translate-y-1/2 px-3 text-xs" onClick={() => setQuery("")}>{content.clearSearch}</Button> : null}
            </label>
          </div>
          <div className="rounded-lg border bg-muted/20 px-4 py-3 text-xs leading-5 text-muted-foreground">
            <strong className="block text-sm font-medium text-foreground">{content.choosePath}</strong>
            <span className="mt-1 block">{content.choosePathDescription}</span>
          </div>
        </div>
      </div>

      {!searching ? <MobileContents content={content} /> : null}

      <div className="mt-6 grid min-w-0 gap-8 lg:grid-cols-[15rem_minmax(0,1fr)] lg:items-start">
        <aside className="sticky top-24 hidden max-h-[calc(100dvh-7rem)] overflow-y-auto pr-5 lg:block" aria-label={content.contents}>
          <HelpContents content={content} />
        </aside>
        <div className="min-w-0">
          {searching ? (
            <SearchResults content={content} query={query} count={resultCount} guides={results.guides} glossary={results.glossary} onClear={() => setQuery("")} />
          ) : (
            <div className="space-y-12">
              <Overview content={content} />
              <RolePaths content={content} />
              {content.guides.map((guide) => <GuideSection key={guide.id} content={content} guide={guide} />)}
              <Glossary content={content} entries={content.glossary} />
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

function MobileContents({ content }: { content: HelpContent }) {
  return (
    <details className="group mt-4 rounded-lg border bg-card lg:hidden">
      <summary className="flex min-h-12 cursor-pointer list-none items-center justify-between px-4 text-sm font-medium outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring [&::-webkit-details-marker]:hidden">
        <span className="flex items-center gap-2"><CircleHelp className="size-4 text-primary" />{content.contents}</span>
        <ArrowRight className="size-4 text-muted-foreground transition-transform group-open:rotate-90" />
      </summary>
      <div className="border-t p-4"><HelpContents content={content} compact /></div>
    </details>
  );
}

function HelpContents({ content, compact = false }: { content: HelpContent; compact?: boolean }) {
  const linkClass = "flex min-h-11 items-center rounded-md px-2.5 text-xs text-muted-foreground outline-none hover:bg-muted/60 hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring";
  return (
    <nav>
      {!compact ? <h2 className="px-2.5 text-sm font-semibold">{content.contents}</h2> : null}
      <div className={cn("space-y-4", !compact && "mt-3")}>
        <div>
          <a className={linkClass} href="#overview">{content.overviewTitle}</a>
        </div>
        {content.guides.map((guide) => (
          <div key={guide.id}>
            <a className={cn(linkClass, "font-medium text-foreground")} href={`#guide-${guide.id}`}>{guide.label}</a>
            <div className="ml-2 border-l pl-2">
              {guide.articles.map((article) => <a key={article.id} className={linkClass} href={`#${article.id}`}>{article.title}</a>)}
            </div>
          </div>
        ))}
        <div><a className={cn(linkClass, "font-medium text-foreground")} href="#glossary">{content.glossaryTitle}</a></div>
      </div>
    </nav>
  );
}

function Overview({ content }: { content: HelpContent }) {
  return (
    <section id="overview" className="scroll-mt-24">
      <p className="text-xs font-medium text-primary">{content.overviewLabel}</p>
      <h2 className="mt-1.5 text-2xl font-semibold">{content.overviewTitle}</h2>
      <p className="mt-3 max-w-4xl text-sm leading-7 text-muted-foreground">{content.overviewDescription}</p>
      <div className="mt-6 rounded-xl border bg-card p-5 sm:p-6">
        <div className="flex items-start gap-3"><Network className="mt-0.5 size-5 shrink-0 text-primary" /><div><h3 className="text-base font-semibold">{content.architectureTitle}</h3><p className="mt-1 text-sm leading-6 text-muted-foreground">{content.architectureDescription}</p></div></div>
        <ol className="mt-5 grid gap-0 sm:grid-cols-2 xl:grid-cols-6">
          {content.architecture.map((item, index) => (
            <li key={item.name} className="relative border-l px-4 py-3 first:border-l-0 sm:[&:nth-child(odd)]:border-l-0 xl:[&:nth-child(odd)]:border-l xl:first:border-l-0">
              <span className="font-mono text-[10px] text-primary">{String(index + 1).padStart(2, "0")}</span>
              <strong className="mt-1 block text-sm font-medium">{item.name}</strong>
              <p className="mt-1 text-xs leading-5 text-muted-foreground">{item.description}</p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

function RolePaths({ content }: { content: HelpContent }) {
  return (
    <section aria-labelledby="role-paths-title">
      <h2 id="role-paths-title" className="text-xl font-semibold">{content.choosePath}</h2>
      <p className="mt-1 text-sm leading-6 text-muted-foreground">{content.choosePathDescription}</p>
      <div className="mt-5 grid gap-3 md:grid-cols-3">
        {content.guides.map((guide) => {
          const Icon = ROLE_ICONS[guide.id];
          return (
            <a key={guide.id} href={`#guide-${guide.id}`} className="group flex min-h-44 flex-col rounded-xl border bg-card p-4 outline-none transition-[border-color,box-shadow] hover:border-primary/30 hover:shadow-sm focus-visible:ring-2 focus-visible:ring-ring">
              <span className="grid size-9 place-items-center rounded-lg bg-muted text-primary"><Icon className="size-4.5" /></span>
              <strong className="mt-4 text-sm font-semibold">{guide.label}</strong>
              <span className="mt-1 text-xs leading-5 text-muted-foreground">{guide.summary}</span>
              <span className="mt-auto flex items-center gap-1 pt-4 text-xs font-medium text-primary">{guide.title}<ArrowRight className="size-3.5 transition-transform group-hover:translate-x-0.5" /></span>
            </a>
          );
        })}
      </div>
    </section>
  );
}

function GuideSection({ content, guide, articles = guide.articles }: { content: HelpContent; guide: HelpGuide; articles?: HelpArticle[] }) {
  const Icon = ROLE_ICONS[guide.id];
  return (
    <section id={`guide-${guide.id}`} className="scroll-mt-24">
      <header className="flex items-start gap-4">
        <span className="grid size-11 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary"><Icon className="size-5" /></span>
        <div className="min-w-0"><p className="text-xs font-medium text-primary">{content.guideLabel} / {guide.label}</p><h2 className="mt-1 text-2xl font-semibold">{guide.title}</h2><p className="mt-2 max-w-4xl text-sm leading-6 text-muted-foreground">{guide.summary}</p><p className="mt-2 text-xs font-medium text-foreground">{guide.outcome}</p></div>
      </header>
      <div className="mt-6 divide-y overflow-hidden rounded-xl border bg-card">
        {articles.map((article) => <GuideArticle key={article.id} content={content} article={article} />)}
      </div>
    </section>
  );
}

function GuideArticle({ content, article }: { content: HelpContent; article: HelpArticle }) {
  return (
    <article id={article.id} className="scroll-mt-24 p-5 sm:p-6">
      <h3 className="text-lg font-semibold">{article.title}</h3>
      <p className="mt-1 text-sm leading-6 text-muted-foreground">{article.summary}</p>
      {article.paragraphs?.map((paragraph) => <p key={paragraph} className="mt-4 text-sm leading-7 text-foreground/85">{paragraph}</p>)}
      {article.steps ? <StepList steps={article.steps} /> : null}
      {article.bullets ? <ul className="mt-4 space-y-2">{article.bullets.map((bullet) => <li key={bullet} className="flex gap-2.5 text-sm leading-6 text-foreground/85"><CheckCircle2 className="mt-1 size-4 shrink-0 text-primary" /><span>{bullet}</span></li>)}</ul> : null}
      {article.terms ? <TermRows label={content.keyConcepts} terms={article.terms} /> : null}
      {article.note ? <div className="mt-5 border-l-2 border-primary bg-primary/[0.035] px-4 py-3 text-xs leading-6 text-muted-foreground">{article.note}</div> : null}
      {article.links?.length ? <div className="mt-5 flex flex-wrap items-center gap-2"><span className="mr-1 text-xs text-muted-foreground">{content.relatedPages}</span>{article.links.map((link) => <Button key={link.to} size="sm" variant="outline" className="min-h-11" asChild><Link to={link.to}>{link.label}<ArrowRight /></Link></Button>)}</div> : null}
    </article>
  );
}

function StepList({ steps }: { steps: HelpArticle["steps"] }) {
  return <ol className="mt-5 grid gap-3">{steps?.map((step, index) => <li key={step.title} className="grid grid-cols-[2rem_minmax(0,1fr)] gap-3"><span className="grid size-8 place-items-center rounded-full border bg-muted/30 font-mono text-xs text-primary">{index + 1}</span><div className="pt-1"><strong className="block text-sm font-medium">{step.title}</strong><p className="mt-1 text-xs leading-5 text-muted-foreground">{step.description}</p></div></li>)}</ol>;
}

function TermRows({ label, terms }: { label: string; terms: NonNullable<HelpArticle["terms"]> }) {
  return (
    <div className="mt-5 overflow-hidden rounded-lg border">
      <p className="border-b bg-muted/25 px-4 py-2.5 text-xs font-medium text-muted-foreground">{label}</p>
      <dl className="divide-y">{terms.map((term) => <div key={term.name} className="grid gap-1 px-4 py-3 sm:grid-cols-[10rem_minmax(0,1fr)] sm:gap-5"><dt className="font-mono text-xs font-medium text-foreground">{term.name}</dt><dd className="text-xs leading-5 text-muted-foreground">{term.description}</dd></div>)}</dl>
    </div>
  );
}

function Glossary({ content, entries }: { content: HelpContent; entries: GlossaryEntry[] }) {
  return (
    <section id="glossary" className="scroll-mt-24">
      <p className="text-xs font-medium text-primary">{content.keyConcepts}</p>
      <h2 className="mt-1.5 text-2xl font-semibold">{content.glossaryTitle}</h2>
      <p className="mt-2 max-w-4xl text-sm leading-6 text-muted-foreground">{content.glossaryDescription}</p>
      <div className="mt-6 divide-y overflow-hidden rounded-xl border bg-card">
        {entries.map((entry) => <GlossaryRow key={entry.id} content={content} entry={entry} />)}
      </div>
    </section>
  );
}

function GlossaryRow({ content, entry }: { content: HelpContent; entry: GlossaryEntry }) {
  return (
    <article id={`term-${entry.id}`} className="scroll-mt-24 grid gap-3 p-4 sm:grid-cols-[11rem_minmax(0,1fr)] sm:gap-6 sm:p-5">
      <div><h3 className="font-mono text-sm font-medium">{entry.term}</h3>{entry.aliases.length ? <p className="mt-1 text-[11px] leading-4 text-muted-foreground">{entry.aliases.join(" · ")}</p> : null}</div>
      <div className="min-w-0"><p className="text-sm leading-6">{entry.definition}</p><p className="mt-1 text-xs leading-5 text-muted-foreground">{entry.background}</p><div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-muted-foreground">{entry.audiences.map((audience) => <span key={audience}>{content.audienceLabels[audience]}</span>)}</div></div>
    </article>
  );
}

function SearchResults({ content, query, count, guides, glossary, onClear }: { content: HelpContent; query: string; count: number; guides: Array<{ guide: HelpGuide; articles: HelpArticle[] }>; glossary: GlossaryEntry[]; onClear: () => void }) {
  if (!count) return <div className="flex min-h-80 flex-col items-center justify-center rounded-xl border border-dashed bg-card px-6 text-center"><Search className="size-7 text-muted-foreground" /><h2 className="mt-3 text-base font-semibold">{content.noResultsTitle}</h2><p className="mt-1 max-w-md text-sm leading-6 text-muted-foreground">{content.noResultsDescription}</p><Button className="mt-5 min-h-11" variant="outline" onClick={onClear}>{content.clearSearch}</Button></div>;
  return (
    <section aria-live="polite">
      <div className="flex flex-wrap items-end justify-between gap-3"><div><p className="text-xs font-medium text-primary">{content.searchResults}</p><h2 className="mt-1 text-2xl font-semibold">“{query.trim()}”</h2></div><Badge variant="outline">{count}</Badge></div>
      <div className="mt-7 space-y-10">
        {guides.length ? <section><h3 className="text-sm font-semibold">{content.roleResults}</h3><div className="mt-3 space-y-6">{guides.map((item) => <GuideSection key={item.guide.id} content={content} guide={item.guide} articles={item.articles} />)}</div></section> : null}
        {glossary.length ? <section><h3 className="text-sm font-semibold">{content.glossaryResults}</h3><div className="mt-3 divide-y overflow-hidden rounded-xl border bg-card">{glossary.map((entry) => <GlossaryRow key={entry.id} content={content} entry={entry} />)}</div></section> : null}
      </div>
    </section>
  );
}
