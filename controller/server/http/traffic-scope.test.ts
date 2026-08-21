import { describe, expect, it } from "vitest";

import { assertTrafficScopeSupported } from "./app.js";

describe("Traffic Scope API contract", () => {
  it("accepts catalog fields and the root catch-all", () => {
    expect(() => assertTrafficScopeSupported({ combinator: "and", conditions: [] })).not.toThrow();
    expect(() => assertTrafficScopeSupported({
      combinator: "and",
      conditions: [{ field: "target.environment", key: "", operator: "equals", value: "production" }],
    })).not.toThrow();
  });

  it("rejects fields that Runner cannot resolve and invalid custom keys", () => {
    expect(() => assertTrafficScopeSupported({
      combinator: "and",
      conditions: [{ field: "request_metadata", key: "target.environment", operator: "equals", value: "production" }],
    })).toThrow("not supported by Runner");
    expect(() => assertTrafficScopeSupported({
      combinator: "and",
      conditions: [{ field: "http.header", key: "", operator: "equals", value: "internal" }],
    })).toThrow("requires a key");
  });
});
