import { describe, expect, it } from "vitest";

import { compilerLocation } from "@/lib/compiler-location";

describe("compilerLocation", () => {
  it("reads an explicit Colang source path", () => {
    expect(compilerLocation("customer.co:12:8: undefined Flow")).toEqual({
      path: "customer.co",
      line: 12,
      column: 8,
    });
  });

  it("reads the NeMo parser line and column fallback", () => {
    expect(
      compilerLocation(
        "Unexpected token Token('_NEWLINE') at line 3, column 12.",
      ),
    ).toEqual({ path: "main.co", line: 3, column: 12 });
  });
});
