import { describe, expect, it } from "vitest";

import {
  filterMultiSelectOptions,
  isMultiSelectOptionDisabled,
  sortMultiSelectOptions,
  type MultiSelectOption,
} from "./multi-select-options";

const options: MultiSelectOption[] = [
  { label: "Code generation", meta: "Connected", value: "code-generation" },
  { label: "Analytics", keywords: ["reporting"], value: "analytics" },
  { label: "Artifact search", value: "artifact-search" },
];

describe("multi-select option behavior", () => {
  it("sorts the menu alphabetically without changing the source array", () => {
    expect(sortMultiSelectOptions(options, "en").map((option) => option.label)).toEqual([
      "Analytics",
      "Artifact search",
      "Code generation",
    ]);
    expect(options[0]?.label).toBe("Code generation");
  });

  it("filters labels, metadata, and hidden search keywords case-insensitively", () => {
    expect(filterMultiSelectOptions(options, "  ART").map((option) => option.value)).toEqual(["artifact-search"]);
    expect(filterMultiSelectOptions(options, "connected").map((option) => option.value)).toEqual(["code-generation"]);
    expect(filterMultiSelectOptions(options, "REPORT").map((option) => option.value)).toEqual(["analytics"]);
  });

  it("keeps selected options removable after reaching the selection limit", () => {
    expect(isMultiSelectOptionDisabled(options[2]!, ["analytics", "artifact-search"], 2)).toBe(false);
    expect(isMultiSelectOptionDisabled(options[0]!, ["analytics", "artifact-search"], 2)).toBe(true);
  });
});
