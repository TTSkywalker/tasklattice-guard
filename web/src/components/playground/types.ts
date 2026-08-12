import type { PlaygroundProbeResult } from "@/lib/api";

export type ProbePhase = "input" | "output";

export type PlaygroundTurn = {
  id: string;
  phase: ProbePhase;
  content: string;
  result: PlaygroundProbeResult;
};
