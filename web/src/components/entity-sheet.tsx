import type { ReactNode } from "react";

import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { cn } from "@/lib/utils";

const widthClasses = {
  md: "!w-full !max-w-none sm:!w-[min(92vw,40rem)] sm:!max-w-[40rem]",
  lg: "!w-full !max-w-none sm:!w-[min(92vw,48rem)] sm:!max-w-[48rem]",
  xl: "!w-full !max-w-none sm:!w-[min(92vw,56rem)] sm:!max-w-[56rem]",
} as const;

export function EntitySheet({
  bodyClassName,
  children,
  description,
  eyebrow,
  footer,
  onOpenChange,
  open,
  title,
  width = "lg",
}: {
  bodyClassName?: string;
  children: ReactNode;
  description: ReactNode;
  eyebrow: string;
  footer: ReactNode;
  onOpenChange: (open: boolean) => void;
  open: boolean;
  title: ReactNode;
  width?: keyof typeof widthClasses;
}) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className={cn(
          "gap-0 border-l bg-background shadow-[var(--shadow-overlay)] [&>button]:size-11 [&>button]:rounded-lg",
          widthClasses[width],
        )}
      >
        <SheetHeader className="shrink-0 gap-1.5 border-b bg-card px-4 py-5 pr-14 sm:px-6 sm:pr-16">
          <p className="text-xs font-medium text-primary">{eyebrow}</p>
          <SheetTitle className="font-display text-2xl font-semibold tracking-[-0.015em] text-foreground">
            {title}
          </SheetTitle>
          <SheetDescription className="max-w-2xl leading-5 text-muted-foreground">
            {description}
          </SheetDescription>
        </SheetHeader>

        <div
          className={cn(
            "min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 py-5 sm:px-6",
            bodyClassName,
          )}
        >
          {children}
        </div>

        <SheetFooter className="shrink-0 flex-row items-center justify-end gap-2 border-t bg-card px-4 py-4 sm:px-6 [&_[data-slot=button]]:min-h-11">
          {footer}
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}
