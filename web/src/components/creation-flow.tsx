import type { ReactNode } from "react";
import { Check } from "lucide-react";

import {
  Stepper,
  StepperContent,
  StepperDescription,
  StepperIndicator,
  StepperItem,
  StepperNav,
  StepperPanel,
  StepperSeparator,
  StepperTitle,
  StepperTrigger,
} from "@/components/reui/stepper";
import { useIsMobile } from "@/hooks/use-mobile";
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
  orientation = "horizontal",
}: {
  children: ReactNode;
  currentStep: number;
  onStepChange: (step: number) => void;
  progressLabel: string;
  steps: readonly CreationStep[];
  orientation?: "horizontal" | "sidebar";
}) {
  const sidebar = orientation === "sidebar";
  const vertical = sidebar && !useIsMobile();
  const activeValue = currentStep + 1;

  function changeStep(value: number) {
    const next = value - 1;
    if (next <= currentStep) onStepChange(next);
  }

  return (
    <Stepper
      value={activeValue}
      onValueChange={changeStep}
      orientation={vertical ? "vertical" : "horizontal"}
      indicators={{ completed: <Check className="size-3.5" /> }}
      className={cn(
        "min-h-full",
        vertical ? "grid grid-cols-[15rem_minmax(0,1fr)]" : "flex flex-col",
      )}
    >
      <StepperNav
        aria-label={progressLabel}
        className={cn(
          vertical
            ? "sticky top-0 min-h-full w-full self-start border-r bg-muted/20 px-4 py-5"
            : "w-full gap-0 overflow-x-auto border-b bg-muted/20 px-3 py-3 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden",
        )}
      >
        {steps.map((step, index) => (
          <StepperItem
            key={step.label}
            step={index + 1}
            disabled={index > currentStep}
            className={cn(
              "relative justify-start",
              vertical ? "min-h-[4.75rem] w-full items-start last:min-h-0" : "min-w-28 items-center",
            )}
          >
            <StepperTrigger
              aria-current={index === currentStep ? "step" : undefined}
              className={cn(
                "relative z-10 min-h-11 text-left transition-colors",
                vertical
                  ? "w-full items-start gap-3 rounded-lg px-2 py-2 hover:bg-background/70 data-[state=active]:bg-background data-[state=active]:shadow-xs"
                  : "w-full flex-col gap-1.5 rounded-lg px-2 py-1 text-center hover:bg-background/70",
              )}
            >
              <StepperIndicator
                className={cn(
                  "size-7 border-2 border-border bg-background font-mono text-[11px] text-muted-foreground",
                  "data-[state=active]:border-primary data-[state=active]:bg-background data-[state=active]:text-primary",
                  "data-[state=completed]:border-primary data-[state=completed]:bg-primary data-[state=completed]:text-primary-foreground",
                )}
              >
                {index + 1}
              </StepperIndicator>
              <span className={cn("min-w-0", !vertical && "max-w-28")}>
                <StepperTitle className="truncate text-sm data-[state=active]:text-primary data-[state=inactive]:text-muted-foreground">
                  {step.label}
                </StepperTitle>
                {vertical ? (
                  <StepperDescription className="mt-1 text-xs leading-4 data-[state=inactive]:text-muted-foreground/65">
                    {step.description}
                  </StepperDescription>
                ) : null}
              </span>
            </StepperTrigger>
            {index < steps.length - 1 ? (
              <StepperSeparator
                className={cn(
                  "group-data-[state=completed]/step:bg-primary",
                  vertical
                    ? "absolute top-9 bottom-0 left-[1.375rem] h-auto w-px -translate-x-1/2"
                    : "absolute top-[1.375rem] left-[calc(50%+1rem)] h-px w-[calc(100%-2rem)] -translate-y-1/2",
                )}
              />
            ) : null}
          </StepperItem>
        ))}
      </StepperNav>

      <StepperPanel className="min-w-0 bg-background">
        <StepperContent value={activeValue} className={cn("min-w-0", sidebar ? "p-4 sm:p-6" : "pt-6")}>
          {children}
        </StepperContent>
      </StepperPanel>
    </Stepper>
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
