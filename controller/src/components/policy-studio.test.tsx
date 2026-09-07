import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { PolicyImport } from "@/lib/policy-transfer";
import { protectionDirectoryIds } from "../../shared/protection-map";
import { PolicyStudioSheet } from "./policy-studio";

vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("@/hooks/use-mobile", () => ({ useIsMobile: () => false }));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { email: "author@example.test", role: "admin" } }) }));
const api = vi.hoisted(() => ({ create: vi.fn(), update: vi.fn(), validate: vi.fn(), run: vi.fn(), publish: vi.fn() }));
vi.mock("@/lib/api", async original => ({ ...await original<typeof import("@/lib/api")>(),
  getActionCatalog: async () => ({ items: [] }), createProgrammablePolicy: api.create,
  updateProgrammablePolicy: api.update, validateProgrammablePolicy: api.validate,
  runProgrammablePolicyValidation: api.run, publishProgrammablePolicy: api.publish,
}));

const imported: PolicyImport = {
  name: "Synthetic check", description: "Directory regression", owner: "author@example.test", sourcePolicyId: null, sourceDraftRevision: null,
  draft: { guardrail_category: "pii_detection", colang_version: "2.x", sources: [{ path: "main.co", content: "flow check_request $text\n  pass" }],
    parameter_schema: [], action_references: [], evaluation_contracts: [], prompt_dependencies: [], execution_contract: [],
    rail_bindings: [{ rail_type: "input", flow_name: "check_request", execution_mode: "detect", on_unsafe: "reject",
      parallel_group: null, priority: null, timeout_ms: 500, failure_mode: "fail_closed", required: true, depends_on: [] }],
    test_cases: [{ id: "one", name: "Safe", description: "", rail_type: "input", content: "Hello", expected_decision: "allow",
      covered_rule_ids: ["flow/input/check_request"], case_type: "input_rail", required: true, expected_failure: null,
      concurrency_group: null, trusted_instruction: "", use_guardrail_instruction: false, for_each: null,
      target_source: "user_input", query: "", grounding_sources: [], expected_reasoning_result: null }],
  },
};
function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><PolicyStudioSheet open policy={null} imported={imported} onOpenChange={() => {}} onSaved={async () => {}} /></QueryClientProvider>);
}
function review() {
  fireEvent.click(screen.getByRole("button", { name: "common.next" }));
  fireEvent.click(screen.getByRole("button", { name: "common.next" }));
}
async function selectDirectory(directory: string) {
  fireEvent.keyDown(screen.getByRole("combobox", { name: "policyStudio.protectionDirectory" }), { key: "Enter" });
  fireEvent.click(await screen.findByRole("option", { name: `protection.directories.${directory}` }));
}
afterEach(cleanup);
beforeEach(() => {
  vi.clearAllMocks();
  HTMLElement.prototype.scrollIntoView = vi.fn();
  api.create.mockResolvedValue({ id: "regression" }); api.update.mockResolvedValue({ id: "regression" });
  api.validate.mockResolvedValue({}); api.run.mockResolvedValue({ status: "passed", draft_revision: 1, results: [] });
});

describe("Policy Studio business directory", () => {
  it("keeps a stable accessible label when a multiline field is edited", () => {
    show();
    const field = screen.getByRole("textbox", { name: "policyStudio.description *" });
    fireEvent.change(field, { target: { value: "Changed description" } });
    expect(screen.getByRole("textbox", { name: "policyStudio.description *" })).toBe(field);
    expect(field.closest("label")).toBeNull();
  });

  it("offers the same eight directories as the protection map, with the existing classification selected", async () => {
    show();
    const trigger = screen.getByRole("combobox", { name: "policyStudio.protectionDirectory" });
    expect(trigger.textContent).toContain("protection.directories.privacy");
    fireEvent.keyDown(trigger, { key: "Enter" });
    expect(await screen.findAllByRole("option")).toHaveLength(8);
    for (const directory of protectionDirectoryIds) expect(screen.getByRole("option", { name: `protection.directories.${directory}` })).toBeTruthy();
    expect(screen.queryByText("policyStudio.guardrailCategory")).toBeNull();
  });

  it("persists the chosen directory, shows it in review and invalidates validation when it changes", async () => {
    show(); await selectDirectory("content_filters"); review();
    fireEvent.click(screen.getByRole("button", { name: "policyStudio.validateAndRun" }));
    await screen.findByRole("button", { name: "policyStudio.publish" });
    expect(api.create).toHaveBeenCalledWith(expect.objectContaining({ draft: { ...imported.draft, protection_directory: "content_filters" } }));
    expect(screen.getByText("protection.directories.content_filters")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "common.previous" }));
    fireEvent.click(screen.getByRole("button", { name: "common.previous" }));
    await selectDirectory("application_injection"); review();
    expect(screen.queryByRole("button", { name: "policyStudio.publish" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "policyStudio.validateAndRun" }));
    await waitFor(() => expect(api.update).toHaveBeenCalledWith("regression", expect.objectContaining({
      draft: { ...imported.draft, protection_directory: "application_injection" },
    })));
  });

  it("retains the directory and source after a save failure and allows a successful retry", async () => {
    api.create.mockRejectedValueOnce(new Error("Fixture connection unavailable"));
    show(); await selectDirectory("business_rules"); review();
    fireEvent.click(screen.getByRole("button", { name: "policyStudio.validateAndRun" }));
    await screen.findAllByText("Fixture connection unavailable");
    expect(api.publish).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "policyStudio.validateAndRun" }));
    await screen.findByRole("button", { name: "policyStudio.publish" });
    expect(api.create.mock.calls[0]).toEqual(api.create.mock.calls[1]);
    expect(screen.getByText("protection.directories.business_rules")).toBeTruthy();
  });
});
