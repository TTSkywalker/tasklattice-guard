import type { RuleGroupType } from "react-querybuilder";

export type TrafficFilterOperator = "equals" | "contains" | "starts_with" | "glob";

export type TrafficFilterFieldDefinition = {
  id: string;
  group: "request" | "authentication" | "http" | "model" | "litellm" | "a2a";
  source: "field" | "header" | "jwt_claim";
  key: string;
  operators: TrafficFilterOperator[];
  values: string[];
  custom_key?: boolean;
};

export type TrafficFilterRule = {
  field: string;
  key?: string;
  operator: TrafficFilterOperator;
  value: string;
};

export type TrafficFilterExpression = {
  combinator: "and" | "or";
  rules: Array<TrafficFilterRule | TrafficFilterExpression>;
};

export type TrafficFilterQuery = RuleGroupType;

export type TrafficFilterConflict = {
  path: number[];
  field: string;
  key: string;
  values: string[];
};

export type TrafficFilterBuilderProps = {
  definitions: TrafficFilterFieldDefinition[];
  query: TrafficFilterQuery;
  matchAll: boolean;
  onQueryChange: (query: TrafficFilterQuery) => void;
  onMatchAllChange: (matchAll: boolean) => void;
  maxRules?: number;
  className?: string;
};
