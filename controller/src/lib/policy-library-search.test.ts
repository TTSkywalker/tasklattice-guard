import { expect, it } from "vitest";
import { policyLibrarySearch } from "./policy-library-search";

it("preserves integer custom versions and semantic versions after JSON URL parsing", () => {
  expect(policyLibrarySearch({ policy: "custom", version: 1 })).toEqual({ policy: "custom", version: "1" });
  expect(policyLibrarySearch({ policy: "builtin", version: "1.95.0" }).version).toBe("1.95.0");
  for (const version of [null, false, 1.5, -1, [], {}]) expect(policyLibrarySearch({ version }).version).toBeUndefined();
});
