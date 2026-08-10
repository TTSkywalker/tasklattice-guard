import { describe, expect, it } from "vitest";

import {
  getTrafficFilterConflicts,
  isTrafficFilterValid,
  setTrafficGroupCombinator,
  toWorkloadFilterExpression,
} from "./model";
import type { TrafficFilterFieldDefinition, TrafficFilterQuery } from "./types";

const definitions: TrafficFilterFieldDefinition[] = [
  {
    id: "protocol",
    group: "request",
    source: "field",
    key: "protocol",
    operators: ["equals"],
    values: ["http", "litellm", "a2a"],
  },
  {
    id: "http.header",
    group: "http",
    source: "header",
    key: "",
    operators: ["equals", "contains"],
    values: [],
    custom_key: true,
  },
];

describe("traffic filter model", () => {
  it("detects mutually exclusive equals rules inside an AND group", () => {
    const query: TrafficFilterQuery = {
      combinator: "and",
      rules: [
        { field: "protocol", operator: "equals", value: "http" },
        { field: "protocol", operator: "equals", value: "a2a" },
      ],
    };

    expect(getTrafficFilterConflicts(query, definitions)).toEqual([
      { path: [], field: "protocol", key: "", values: ["http", "a2a"] },
    ]);
    expect(isTrafficFilterValid(query, definitions, false)).toBe(false);
  });

  it("allows the same alternatives inside an OR group", () => {
    const query: TrafficFilterQuery = {
      combinator: "or",
      rules: [
        { field: "protocol", operator: "equals", value: "http" },
        { field: "protocol", operator: "equals", value: "a2a" },
      ],
    };

    expect(getTrafficFilterConflicts(query, definitions)).toEqual([]);
    expect(isTrafficFilterValid(query, definitions, false)).toBe(true);
  });

  it("updates only the conflicting nested group", () => {
    const query: TrafficFilterQuery = {
      combinator: "and",
      rules: [
        { field: "protocol", operator: "equals", value: "http" },
        {
          combinator: "and",
          rules: [
            { field: "protocol", operator: "equals", value: "http" },
            { field: "protocol", operator: "equals", value: "a2a" },
          ],
        },
      ],
    };

    const updated = setTrafficGroupCombinator(query, [1], "or");

    expect(updated.combinator).toBe("and");
    expect(updated.rules[1]).toMatchObject({ combinator: "or" });
  });

  it("converts custom request attributes into the backend expression", () => {
    const query: TrafficFilterQuery = {
      combinator: "and",
      rules: [
        { field: "protocol", operator: "equals", value: "http" },
        {
          combinator: "or",
          rules: [
            {
              field: "http.header",
              operator: "equals",
              value: { key: "x-app-id", value: "finance-agent" },
            },
          ],
        },
      ],
    };

    expect(toWorkloadFilterExpression(query, definitions)).toEqual({
      combinator: "and",
      rules: [
        { field: "protocol", operator: "equals", value: "http" },
        {
          combinator: "or",
          rules: [
            {
              field: "http.header",
              key: "x-app-id",
              operator: "equals",
              value: "finance-agent",
            },
          ],
        },
      ],
    });
  });
});
