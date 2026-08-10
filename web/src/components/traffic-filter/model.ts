import { isRuleGroup, type RuleGroupType, type RuleType } from "react-querybuilder";

import type {
  TrafficFilterConflict,
  TrafficFilterExpression,
  TrafficFilterFieldDefinition,
  TrafficFilterOperator,
  TrafficFilterQuery,
  TrafficFilterRule,
} from "./types";

type CustomRuleValue = { key: string; value: string };

export function createTrafficFilterQuery(
  definitions: TrafficFilterFieldDefinition[],
): TrafficFilterQuery {
  const definition = definitions.find((item) => item.id === "protocol") ?? definitions[0];
  return {
    combinator: "and",
    rules: definition ? [createTrafficRule(definition)] : [],
  };
}

export function createTrafficRule(definition: TrafficFilterFieldDefinition): RuleType {
  return {
    field: definition.id,
    operator: definition.operators[0],
    value: definition.custom_key ? { key: "", value: "" } : definition.values[0] ?? "",
  };
}

export function toWorkloadFilterExpression(
  query: TrafficFilterQuery,
  definitions: TrafficFilterFieldDefinition[],
): TrafficFilterExpression {
  return {
    combinator: query.combinator === "or" ? "or" : "and",
    rules: query.rules.map((item) => {
      if (isRuleGroup(item)) return toWorkloadFilterExpression(item, definitions);
      const definition = definitions.find((candidate) => candidate.id === item.field);
      const encoded = customRuleValue(item.value);
      return {
        field: item.field,
        ...(definition?.custom_key ? { key: encoded.key.trim() } : {}),
        operator: item.operator as TrafficFilterOperator,
        value: (definition?.custom_key ? encoded.value : String(item.value ?? "")).trim(),
      } satisfies TrafficFilterRule;
    }),
  };
}

export function isTrafficFilterValid(
  query: TrafficFilterQuery,
  definitions: TrafficFilterFieldDefinition[],
  matchAll: boolean,
  maxRules = 16,
): boolean {
  if (matchAll) return true;
  const count = countTrafficRules(query);
  if (!count || count > maxRules || getTrafficFilterConflicts(query, definitions).length) return false;
  return validGroup(query, definitions, 1);
}

export function countTrafficRules(query: RuleGroupType | TrafficFilterExpression): number {
  return query.rules.reduce(
    (total, item) => total + (isExpressionGroup(item) ? countTrafficRules(item) : 1),
    0,
  );
}

export function getTrafficFilterConflicts(
  query: TrafficFilterQuery,
  definitions: TrafficFilterFieldDefinition[],
): TrafficFilterConflict[] {
  const definitionById = new Map(definitions.map((item) => [item.id, item]));
  const conflicts: TrafficFilterConflict[] = [];

  function visit(group: RuleGroupType, path: number[]) {
    if (group.combinator === "and") {
      const equalities = new Map<string, { field: string; key: string; values: Set<string> }>();
      for (const item of group.rules) {
        if (isRuleGroup(item) || item.operator !== "equals") continue;
        const definition = definitionById.get(item.field);
        if (!definition) continue;
        const encoded = customRuleValue(item.value);
        const key = definition.custom_key ? encoded.key.trim() : "";
        if (definition.custom_key && !key) continue;
        const identity = `${item.field}\u0000${key}`;
        const current = equalities.get(identity) ?? {
          field: item.field,
          key,
          values: new Set<string>(),
        };
        current.values.add(definition.custom_key ? encoded.value.trim() : String(item.value ?? "").trim());
        equalities.set(identity, current);
      }
      for (const item of equalities.values()) {
        if (item.values.size > 1) {
          conflicts.push({ path, field: item.field, key: item.key, values: [...item.values] });
        }
      }
    }
    group.rules.forEach((item, index) => {
      if (isRuleGroup(item)) visit(item, [...path, index]);
    });
  }

  visit(query, []);
  return conflicts;
}

export function setTrafficGroupCombinator(
  query: TrafficFilterQuery,
  path: number[],
  combinator: "and" | "or",
): TrafficFilterQuery {
  if (!path.length) return { ...query, combinator };
  const [index, ...remaining] = path;
  return {
    ...query,
    rules: query.rules.map((item, itemIndex) => {
      if (itemIndex !== index || !isRuleGroup(item)) return item;
      return setTrafficGroupCombinator(item, remaining, combinator);
    }),
  };
}

export function customRuleValue(value: unknown): CustomRuleValue {
  if (value && typeof value === "object" && "key" in value && "value" in value) {
    return { key: String(value.key ?? ""), value: String(value.value ?? "") };
  }
  return { key: "", value: String(value ?? "") };
}

function validGroup(
  query: RuleGroupType,
  definitions: TrafficFilterFieldDefinition[],
  depth: number,
): boolean {
  if (depth > 3 || !query.rules.length) return false;
  return query.rules.every((item) => {
    if (isRuleGroup(item)) return validGroup(item, definitions, depth + 1);
    const definition = definitions.find((candidate) => candidate.id === item.field);
    if (!definition || !definition.operators.includes(item.operator as TrafficFilterOperator)) return false;
    const encoded = customRuleValue(item.value);
    return definition.custom_key
      ? Boolean(encoded.key.trim() && encoded.value.trim())
      : Boolean(String(item.value ?? "").trim());
  });
}

function isExpressionGroup(value: unknown): value is RuleGroupType | TrafficFilterExpression {
  return Boolean(value && typeof value === "object" && "rules" in value);
}
