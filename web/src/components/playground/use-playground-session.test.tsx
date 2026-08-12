import type { PropsWithChildren } from "react";
import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";

import type { PlaygroundTurn } from "@/components/playground/types";
import { usePlaygroundSession } from "@/components/playground/use-playground-session";

const turn = {
  interaction_id: "interaction-1",
  state: "completed",
  user_message: "Hello",
  effective_user_message: "Hello",
  assistant_message: "Hi",
} as PlaygroundTurn;

describe("usePlaygroundSession", () => {
  it("retains Guardrail-scoped turns across page unmounts until cleared", async () => {
    const client = new QueryClient();
    const wrapper = ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
    const first = renderHook(() => usePlaygroundSession("guardrail-1"), { wrapper });

    act(() => first.result.current.appendTurn(turn));
    await waitFor(() => expect(first.result.current.turns).toEqual([turn]));
    first.unmount();

    const restored = renderHook(() => usePlaygroundSession("guardrail-1"), { wrapper });
    expect(restored.result.current.turns).toEqual([turn]);

    act(() => restored.result.current.clearTurns());
    await waitFor(() => expect(restored.result.current.turns).toEqual([]));
  });
});
