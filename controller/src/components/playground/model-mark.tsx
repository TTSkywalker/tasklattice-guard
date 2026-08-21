import { Bot } from "lucide-react";

import type { PlaygroundModel } from "@/lib/api";
import { cn } from "@/lib/utils";

export function ModelMark({ model, className }: { model?: Pick<PlaygroundModel, "provider" | "icon"> | null; className?: string }) {
  if (model?.icon === "deepseek" || model?.provider.toLowerCase() === "deepseek") {
    return <img src="/assets/models/deepseek.svg" alt="" className={cn("size-5 object-contain", className)} />;
  }
  return <Bot aria-hidden="true" className={cn("size-5 text-muted-foreground", className)} />;
}
