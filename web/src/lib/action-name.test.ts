import { describe, expect, it } from "vitest";

import { compactActionName } from "./action-name";

describe("compactActionName", () => {
  it("removes redundant product and type affixes from runtime Action identifiers", () => {
    expect(compactActionName("TaskLatticeBuiltinContentFilterAction")).toBe("BuiltinContentFilter");
    expect(compactActionName("PolicyRuleAction")).toBe("PolicyRule");
  });

  it("does not collapse a name made only from the removable affixes", () => {
    expect(compactActionName("TaskLatticeAction")).toBe("TaskLatticeAction");
  });
});
