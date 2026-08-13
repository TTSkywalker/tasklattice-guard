import type { RuleGroupType } from "react-querybuilder";

export type TrafficScopeOperator = "equals" | "contains" | "starts_with" | "glob";

export type TrafficScopeFieldDefinition = {
  id: string;
  group: "request" | "authentication" | "http" | "model" | "litellm" | "a2a";
  source: "field" | "header" | "jwt_claim";
  key: string;
  operators: TrafficScopeOperator[];
  values: string[];
  custom_key?: boolean;
};

export type TrafficCondition = {
  field: string;
  key?: string;
  operator: TrafficScopeOperator;
  value: string;
};

export type TrafficScopeExpression = {
  combinator: "and" | "or";
  conditions: Array<TrafficCondition | TrafficScopeExpression>;
};

export type TrafficScopeQuery = RuleGroupType;

export type TrafficScopeConflict = {
  path: number[];
  field: string;
  key: string;
  values: string[];
};

export type TrafficScopeBuilderProps = {
  definitions: TrafficScopeFieldDefinition[];
  query: TrafficScopeQuery;
  onQueryChange: (query: TrafficScopeQuery) => void;
  maxRules?: number;
  className?: string;
};
