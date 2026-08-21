import { fireEvent, render, screen } from "@testing-library/react";
import i18next from "i18next";
import { I18nextProvider, initReactI18next } from "react-i18next";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { TrafficScopeBuilder } from "./traffic-scope-builder";
import type { TrafficScopeBuilderProps, TrafficScopeFieldDefinition } from "./types";

const definitions: TrafficScopeFieldDefinition[] = [
  {
    id: "protocol",
    group: "request",
    source: "field",
    key: "protocol",
    operators: ["equals"],
    values: ["http", "a2a"],
  },
];

const conflictQuery: TrafficScopeBuilderProps["query"] = {
  combinator: "and",
  rules: [
    { field: "protocol", operator: "equals", value: "http" },
    { field: "protocol", operator: "equals", value: "a2a" },
  ],
};

const testI18n = i18next.createInstance();
const labels: Record<string, string> = {
  "deployments.trafficScopeBuilder.title": "Traffic Scope",
  "deployments.trafficScopeBuilder.description": "Build a Traffic Scope.",
  "deployments.trafficScopeBuilder.expressionDescription": "Match requests with these conditions.",
  "deployments.trafficScopeBuilder.allConditions": "Match all (AND)",
  "deployments.trafficScopeBuilder.anyCondition": "Match any (OR)",
  "deployments.trafficScopeBuilder.add": "Add condition",
  "deployments.trafficScopeBuilder.addGroup": "Add group",
  "deployments.trafficScopeBuilder.remove": "Remove condition",
  "deployments.trafficScopeBuilder.removeGroup": "Remove group",
  "deployments.trafficScopeBuilder.ruleRelation": "Rule relation",
  "deployments.trafficScopeBuilder.field": "Request field",
  "deployments.trafficScopeBuilder.operator": "Operator",
  "deployments.trafficScopeBuilder.value": "Value",
  "deployments.trafficScopeBuilder.conflictTitle": "This group cannot match",
  "deployments.trafficScopeBuilder.exclusiveEqualsConflict": "{{field}} cannot equal {{values}} at the same time.",
  "deployments.trafficScopeBuilder.changeGroupToOr": "Change this group to OR",
  "deployments.trafficScopeFields.protocol": "Protocol",
  "deployments.trafficScopeGroups.request": "Request",
  "deployments.trafficScopeOperators.equals": "equals",
};

function renderBuilder(props: TrafficScopeBuilderProps) {
  return render(<I18nextProvider i18n={testI18n}><TrafficScopeBuilder {...props} /></I18nextProvider>);
}

describe("TrafficScopeBuilder", () => {
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
      onQueryChange: vi.fn(),
    });

    expect(screen.getByRole("heading", { name: "Traffic Scope" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Add condition" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Add group" })).toBeTruthy();
    expect(screen.getByText("1 / 16")).toBeTruthy();
    expect(screen.queryByText("All traffic")).toBeNull();
  });

  it("explains an impossible AND group and offers one-click recovery", () => {
    const onQueryChange = vi.fn();
    renderBuilder({
      definitions,
      query: conflictQuery,
      onQueryChange,
    });

    expect(screen.getByRole("alert").textContent).toContain("Protocol cannot equal http / a2a at the same time.");
    fireEvent.click(screen.getByRole("button", { name: "Change this group to OR" }));
    expect(onQueryChange).toHaveBeenCalledWith(expect.objectContaining({ combinator: "or" }));
  });
});
