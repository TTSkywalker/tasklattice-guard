import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Integration, IntegrationRegistration } from "@/lib/api";

import { CreateIntegrationSheet, SetupChecklist } from "./integrations";

const createIntegrationMock = vi.fn();
const getIntegrationMock = vi.fn();

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, values?: Record<string, string | number>) => {
      const labels: Record<string, string> = {
        "common.cancel": "Cancel",
        "common.close": "Close",
        "integrations.register": "Add integration",
        "integrations.registering": "Registering…",
        "integrations.registerDescription": "Register one concrete AI Gateway instance.",
        "integrations.setupTitle": "Set up Gateway connection",
        "integrations.setupDescription": "Complete connection setup.",
        "integrations.name": "Integration name",
        "integrations.namePlaceholder": "Corporate AI Gateway",
        "integrations.integrationProtocol": "Adapter protocol",
        "integrations.adapters.litellm-generic-guardrail": "LiteLLM Generic Guardrail API",
        "integrations.adapterDescriptions.litellm-generic-guardrail": "Native callbacks from LiteLLM Proxy.",
        "integrations.credential": "Credential",
        "integrations.setupChecklist": "Gateway setup checklist",
        "integrations.stepsComplete": "{{count}} / 3 complete",
        "integrations.setupStatuses.awaiting_input": "Awaiting input",
        "integrations.setupStatuses.verified": "Verified",
        "integrations.saveCredential": "Save the credential",
        "integrations.saveCredentialDescription": "Store this value as {{env}}.",
        "integrations.oneTimeCredential": "One-time credential",
        "integrations.oneTimeCredentialDescription": "Shown once.",
        "integrations.copyCredential": "Copy credential",
        "integrations.credentialStoredConfirmation": "I stored this credential in a secure location",
        "integrations.credentialSaved": "Credential saved",
        "integrations.credentialSavedDescription": "The complete value is hidden. Only its non-secret hint remains.",
        "integrations.revealCredential": "Reveal credential",
        "integrations.hideCredential": "Hide credential",
        "integrations.configureAdapter": "Configure {{adapter}}",
        "integrations.configureAdapterDescription": "Deploy the generated configuration.",
        "integrations.configureLiteLLMYaml": "Configure LiteLLM config.yaml",
        "integrations.configureLiteLLMYamlDescription": "Set the generated environment variables, paste the YAML into the Gateway config, then restart or redeploy.",
        "integrations.protocolShort.litellm": "LiteLLM",
        "integrations.litellmConfigurationMethodTitle": "Configuration method: config.yaml",
        "integrations.litellmConfigurationMethodDescription": "Use the generated YAML below as the source of truth.",
        "integrations.litellmAdminUiLabel": "Admin UI mapping:",
        "integrations.litellmAdminUiPath": "Provider → Generic Guardrail API",
        "integrations.litellmAdminUiWarning": "Do not select Custom or another provider.",
        "integrations.apiBaseUrl": "TaskLattice API base URL",
        "integrations.apiBaseEnvironmentVariable": "API base environment assignment",
        "integrations.configurationTemplate": "Adapter configuration",
        "integrations.litellmConfigSnippet": "LiteLLM config.yaml snippet",
        "integrations.copyTemplate": "Copy configuration",
        "integrations.copyItem": "Copy {{item}}",
        "integrations.modes": "Recommended modes",
        "integrations.defaultBehavior": "Application",
        "integrations.defaultOn": "Default on",
        "integrations.failureBehavior": "Failure behavior",
        "integrations.failClosed": "Fail closed",
        "integrations.blockOnError": "block on error",
        "integrations.litellmBaseUrlTitle": "Use the Integration base URL",
        "integrations.litellmBaseUrlDescription": "LiteLLM appends the callback path automatically.",
        "integrations.litellmDocumentation": "Open LiteLLM Generic Guardrail documentation",
        "integrations.verifyCallbacks": "Verify real callbacks",
        "integrations.verifyCallbacksDescription": "Send a real model request.",
        "integrations.inputCallback": "Input callback",
        "integrations.outputCallback": "Output callback",
        "integrations.waiting": "Waiting",
        "integrations.callbacksVerified": "Both callback directions have been received. This Gateway connection is verified.",
        "integrations.complete": "Complete",
        "integrations.finishLater": "Finish later",
        "integrations.openIntegrationDetails": "Open integration",
        "integrations.unsavedCredentialTitle": "This credential has not been marked as saved",
        "integrations.unsavedCredentialDescription": "Leaving permanently hides the complete value.",
        "integrations.keepSettingUp": "Keep setting up",
        "integrations.leaveAndLoseKey": "Leave and lose key",
      };
      return Object.entries(values ?? {}).reduce((label, [name, value]) => label.replace(`{{${name}}}`, String(value)), labels[key] ?? key);
    },
    i18n: { language: "en", exists: () => false },
  }),
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...original,
    createIntegration: (...args: unknown[]) => createIntegrationMock(...args),
    getIntegration: (...args: unknown[]) => getIntegrationMock(...args),
  };
});

function integration(overrides: Partial<Integration> = {}): Integration {
  return {
    id: "11111111-1111-4111-8111-111111111111",
    adapter_id: "litellm-generic-guardrail",
    protocol: "litellm",
    name: "Beijing primary",
    description: "",
    enabled: true,
    key_hint: "tali_••••8NzQ",
    credentials: [{ id: "credential-1", key_hint: "tali_••••8NzQ", created_at: "2026-08-12T08:00:00Z" }],
    setup_status: "awaiting_input",
    runtime_status: "waiting",
    first_seen_at: null,
    input_seen_at: null,
    output_seen_at: null,
    last_seen_at: null,
    last_error_at: null,
    request_count: 0,
    error_count: 0,
    setup: {
      api_base_url: "https://guard.example.com/runtime/v1/integrations/11111111-1111-4111-8111-111111111111",
      callback_url: "https://guard.example.com/runtime/v1/integrations/11111111-1111-4111-8111-111111111111/beta/litellm_basic_guardrail_api",
      auth_header: "x-api-key",
      credential_env_var: "TASKLATTICE_GUARD_API_KEY",
      api_base_env_var: "TASKLATTICE_GUARD_API_BASE",
      recommended_modes: ["pre_call", "post_call"],
      default_on: true,
      fail_on_error: true,
      unreachable_fallback: "fail_closed",
      yaml_template: "litellm_settings:\n  guardrails:\n    - guardrail_name: tasklattice-guard",
    },
    created_at: "2026-08-12T08:00:00Z",
    updated_at: "2026-08-12T08:00:00Z",
    ...overrides,
  };
}

function registration(overrides: Partial<Integration> = {}): IntegrationRegistration {
  return {
    integration: integration(overrides),
    credential: {
      id: "credential-1",
      value: "tali_integration_one_time_value",
      key_hint: "tali_••••8NzQ",
      created_at: "2026-08-12T08:00:00Z",
    },
  };
}

function renderWithProviders(node: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
}

describe("Integration onboarding", () => {
  beforeEach(() => {
    createIntegrationMock.mockReset();
    getIntegrationMock.mockReset();
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("shows every deployable LiteLLM value and real callback verification state", () => {
    const item = integration({
      setup_status: "verified",
      runtime_status: "healthy",
      input_seen_at: "2026-08-12T08:05:00Z",
      output_seen_at: "2026-08-12T08:05:01Z",
      last_seen_at: "2026-08-12T08:05:01Z",
    });

    renderWithProviders(
      <SetupChecklist
        integration={item}
        credential={registration().credential}
        credentialSaved
        configurationCopied
        onCredentialSavedChange={vi.fn()}
        onConfigurationCopied={vi.fn()}
      />,
    );

    expect(screen.getByRole("list", { name: "Gateway setup checklist" })).toBeTruthy();
    expect(screen.queryByText("tali_integration_one_time_value")).toBeNull();
    expect(screen.getByText("tali_••••8NzQ")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Reveal credential" })).toBeTruthy();
    expect(screen.getByText("Configure LiteLLM config.yaml")).toBeTruthy();
    expect(screen.getByText("Provider → Generic Guardrail API")).toBeTruthy();
    expect(screen.getByText("Do not select Custom or another provider.")).toBeTruthy();
    expect(screen.getByText("LiteLLM config.yaml snippet")).toBeTruthy();
    expect(screen.getByText(`TASKLATTICE_GUARD_API_BASE=${item.setup.api_base_url}`)).toBeTruthy();
    expect(screen.getByText(/guardrail_name: tasklattice-guard/)).toBeTruthy();
    expect(screen.getByText("Both callback directions have been received. This Gateway connection is verified.")).toBeTruthy();
    expect(screen.getAllByText("Complete").length).toBe(3);
  });

  it("hides a saved credential and supports explicit reveal and hide without clearing the saved state", async () => {
    const result = registration();
    createIntegrationMock.mockResolvedValue(result);
    getIntegrationMock.mockResolvedValue(result.integration);

    renderWithProviders(<CreateIntegrationSheet open onOpenChange={vi.fn()} onCreated={vi.fn().mockResolvedValue(undefined)} />);

    fireEvent.change(screen.getByPlaceholderText("Corporate AI Gateway"), { target: { value: "Beijing primary" } });
    fireEvent.click(screen.getByRole("button", { name: "Add integration" }));

    expect(await screen.findByText("tali_integration_one_time_value")).toBeTruthy();
    fireEvent.click(screen.getByRole("checkbox", { name: "I stored this credential in a secure location" }));

    expect(screen.queryByText("tali_integration_one_time_value")).toBeNull();
    expect(screen.getByText("tali_••••8NzQ")).toBeTruthy();
    expect(screen.getByText("The complete value is hidden. Only its non-secret hint remains.")).toBeTruthy();
    expect(screen.queryByRole("checkbox", { name: "I stored this credential in a secure location" })).toBeNull();
    expect(screen.getAllByText("Complete")).toHaveLength(1);

    fireEvent.click(screen.getByRole("button", { name: "Reveal credential" }));
    expect(screen.getByText("tali_integration_one_time_value")).toBeTruthy();
    expect(screen.getByText("Credential saved")).toBeTruthy();
    expect(screen.queryByRole("checkbox", { name: "I stored this credential in a secure location" })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Hide credential" }));
    expect(screen.queryByText("tali_integration_one_time_value")).toBeNull();
    expect(screen.getByRole("button", { name: "Reveal credential" })).toBeTruthy();
    expect(screen.getAllByText("Complete")).toHaveLength(1);
  });

  it("protects the one-time credential when creation is closed before it is marked as saved", async () => {
    const result = registration();
    createIntegrationMock.mockResolvedValue(result);
    getIntegrationMock.mockResolvedValue(result.integration);
    const onOpenChange = vi.fn();
    const onCreated = vi.fn().mockResolvedValue(undefined);

    renderWithProviders(<CreateIntegrationSheet open onOpenChange={onOpenChange} onCreated={onCreated} />);

    fireEvent.change(screen.getByPlaceholderText("Corporate AI Gateway"), { target: { value: "Beijing primary" } });
    fireEvent.click(screen.getByRole("button", { name: "Add integration" }));

    await waitFor(() => expect(screen.getByText("tali_integration_one_time_value")).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: "Close" }));

    expect(await screen.findByText("This credential has not been marked as saved")).toBeTruthy();
    expect(onCreated).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Leave and lose key" }));
    await waitFor(() => expect(onCreated).toHaveBeenCalledWith(result.integration, false));
  });
});
