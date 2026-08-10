import { fireEvent, render, screen } from "@testing-library/react";
import i18next from "i18next";
import { I18nextProvider, initReactI18next } from "react-i18next";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { TrafficFilterBuilder } from "./traffic-filter-builder";
import type { TrafficFilterBuilderProps, TrafficFilterFieldDefinition } from "./types";

const definitions: TrafficFilterFieldDefinition[] = [
  {
    id: "protocol",
    group: "request",
    source: "field",
    key: "protocol",
    operators: ["equals"],
    values: ["http", "a2a"],
  },
];

const conflictQuery: TrafficFilterBuilderProps["query"] = {
  combinator: "and",
  rules: [
    { field: "protocol", operator: "equals", value: "http" },
    { field: "protocol", operator: "equals", value: "a2a" },
  ],
};

const testI18n = i18next.createInstance();
const labels: Record<string, string> = {
  "workloads.filterBuilder.title": "Traffic Filter",
  "workloads.filterBuilder.description": "Build a request filter.",
  "workloads.filterBuilder.scope": "Traffic scope",
  "workloads.filterBuilder.filteredTraffic": "Matching traffic",
  "workloads.filterBuilder.allTraffic": "All traffic",
  "workloads.filterBuilder.expressionDescription": "Match requests with these conditions.",
  "workloads.filterBuilder.allConditions": "Match all (AND)",
  "workloads.filterBuilder.anyCondition": "Match any (OR)",
  "workloads.filterBuilder.add": "Add condition",
  "workloads.filterBuilder.addGroup": "Add group",
  "workloads.filterBuilder.remove": "Remove condition",
  "workloads.filterBuilder.removeGroup": "Remove group",
  "workloads.filterBuilder.ruleRelation": "Rule relation",
  "workloads.filterBuilder.field": "Request field",
  "workloads.filterBuilder.operator": "Operator",
  "workloads.filterBuilder.value": "Value",
  "workloads.filterBuilder.conflictTitle": "This group cannot match",
  "workloads.filterBuilder.exclusiveEqualsConflict": "{{field}} cannot equal {{values}} at the same time.",
  "workloads.filterBuilder.changeGroupToOr": "Change this group to OR",
  "workloads.filterFields.protocol": "Protocol",
  "workloads.filterGroups.request": "Request",
  "workloads.filterOperators.equals": "equals",
};

function renderBuilder(props: TrafficFilterBuilderProps) {
  return render(<I18nextProvider i18n={testI18n}><TrafficFilterBuilder {...props} /></I18nextProvider>);
}

describe("TrafficFilterBuilder", () => {
  beforeAll(async () => {
    await testI18n.use(initReactI18next).init({
      lng: "en",
      fallbackLng: false,
      resources: { en: { translation: labels } },
      interpolation: { escapeValue: false },
    });
  });

  it("renders as a standalone compact builder", () => {
    renderBuilder({
      definitions,
      query: { combinator: "and", rules: [{ field: "protocol", operator: "equals", value: "http" }] },
      matchAll: false,
      onQueryChange: vi.fn(),
      onMatchAllChange: vi.fn(),
    });

    expect(screen.getByRole("heading", { name: "Traffic Filter" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Add condition" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Add group" })).toBeTruthy();
    expect(screen.getByText("1 / 16")).toBeTruthy();
  });

  it("explains an impossible AND group and offers one-click recovery", () => {
    const onQueryChange = vi.fn();
    renderBuilder({
      definitions,
      query: conflictQuery,
      matchAll: false,
      onQueryChange,
      onMatchAllChange: vi.fn(),
    });

    expect(screen.getByRole("alert").textContent).toContain("Protocol cannot equal http / a2a at the same time.");
    fireEvent.click(screen.getByRole("button", { name: "Change this group to OR" }));
    expect(onQueryChange).toHaveBeenCalledWith(expect.objectContaining({ combinator: "or" }));
  });
});
