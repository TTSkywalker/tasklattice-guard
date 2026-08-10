import type { ReactNode } from "react";
import { Check } from "lucide-react";

import { cn } from "@/lib/utils";

export type CreationStep = {
  label: string;
  description: string;
};

export function CreationFlow({
  children,
  currentStep,
  onStepChange,
  progressLabel,
  steps,
}: {
  children: ReactNode;
  currentStep: number;
  onStepChange: (step: number) => void;
  progressLabel: string;
  steps: readonly CreationStep[];
}) {
  return (
    <div className="space-y-6">
      <nav aria-label={progressLabel} className="rounded-xl border bg-card p-1 shadow-sm">
        <ol className="grid gap-1" style={{ gridTemplateColumns: `repeat(${steps.length}, minmax(0, 1fr))` }}>
          {steps.map((step, index) => {
            const active = index === currentStep;
            const complete = index < currentStep;
            return (
              <li key={step.label}>
                <button
                  type="button"
                  disabled={index > currentStep}
                  aria-current={active ? "step" : undefined}
                  onClick={() => onStepChange(index)}
                  className={cn(
                    "flex min-h-20 w-full flex-col items-center justify-center gap-2 rounded-lg px-2 py-3 text-center transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50 sm:flex-row sm:justify-start sm:gap-3 sm:px-4 sm:text-left",
                    active && "bg-accent text-accent-foreground",
                    complete && "hover:bg-muted",
                    index > currentStep && "cursor-not-allowed text-muted-foreground/50",
                  )}
                >
                  <span
                    className={cn(
                      "grid size-7 shrink-0 place-items-center rounded-full border bg-card font-mono text-[11px]",
                      (active || complete) && "border-primary bg-primary text-primary-foreground",
                    )}
                  >
                    {complete ? <Check className="size-3.5" /> : index + 1}
                  </span>
                  <span className="min-w-0">
                    <strong className="block whitespace-nowrap text-xs font-medium sm:text-sm">{step.label}</strong>
                    <span className="mt-1 hidden text-xs text-muted-foreground sm:block">
                      {step.description}
                    </span>
                  </span>
                </button>
              </li>
            );
          })}
        </ol>
      </nav>
      {children}
    </div>
  );
}

export function ReviewList({
  items,
}: {
  items: readonly { label: string; value: ReactNode; mono?: boolean }[];
}) {
  return (
    <dl className="divide-y rounded-lg border bg-card px-4 text-sm">
      {items.map((item) => (
        <div key={item.label} className="grid grid-cols-[11rem_minmax(0,1fr)] gap-5 py-3">
          <dt className="text-muted-foreground">{item.label}</dt>
          <dd className={cn("min-w-0 break-words font-medium", item.mono && "font-mono text-xs")}>
            {item.value}
          </dd>
        </div>
      ))}
    </dl>
  );
}
