import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SettingsScreen } from "./settings-screen";

const testMutate = vi.fn();
const saveMutate = vi.fn();
const resetMutate = vi.fn();
const routeMutate = vi.fn();
const state = vi.hoisted(() => ({
  canEdit: true,
  switch: null as unknown,
  azureConfigured: true,
}));

vi.mock("@/components/page-header", () => ({
  PageHeader: ({ title }: { title: string }) => <h1>{title}</h1>,
}));

function role(name: string, overrides: Record<string, unknown> = {}) {
  return {
    role: name,
    provider: "openrouter",
    model: name === "embeddings" ? "openai/text-embedding-3-small" : "deepseek/deepseek-chat",
    base_url: null,
    api_key_masked: "••••1234",
    sources: { provider: "env", model: "env", base_url: "env", api_key: "env" },
    configured: true,
    testable: name !== "transcription",
    switch: null,
    ...overrides,
  };
}

vi.mock("@/lib/api/queries", () => ({
  useModelSettings: () => ({
    isPending: false,
    isError: false,
    isSuccess: true,
    data: {
      can_edit: state.canEdit,
      providers: ["openrouter"],
      route: "openrouter",
      route_source: "env",
      azure_configured: state.azureConfigured,
      roles: [
        role("generation"),
        role("judges"),
        role("embeddings", { switch: state.switch }),
        role("agent"),
        role("tutorials"),
        role("ask_why"),
        role("transcription"),
      ],
    },
  }),
  useProviderModels: () => ({ data: [{ id: "anthropic/claude-haiku-4.5", name: "Haiku" }] }),
  useTestRoleSettings: () => ({ mutateAsync: testMutate, isPending: false, error: null }),
  useSaveRoleSettings: () => ({ mutateAsync: saveMutate, isPending: false, error: null }),
  useResetRoleSettings: () => ({ mutate: resetMutate, isPending: false }),
  useSetRoute: () => ({ mutate: routeMutate, isPending: false, error: null }),
}));

function section(name: string): HTMLElement {
  const heading = screen.getByRole("heading", { name: new RegExp(`^${name}`) });
  return heading.closest("section") as HTMLElement;
}

beforeEach(() => {
  testMutate.mockReset();
  saveMutate.mockReset();
  routeMutate.mockReset();
  state.canEdit = true;
  state.switch = null;
  state.azureConfigured = true;
});

describe("SettingsScreen", () => {
  it("enables Save only after a passing test of the exact values in the form", async () => {
    testMutate.mockResolvedValue({ ok: true, error: null, dimension: null, test_token: "tok" });
    saveMutate.mockResolvedValue({});
    const user = userEvent.setup();
    render(<SettingsScreen />);
    const generation = section("Generation");

    await user.click(within(generation).getByRole("button", { name: "Edit" }));
    await user.type(within(generation).getByLabelText("Model"), "anthropic/claude-haiku-4.5");
    const save = within(generation).getByRole("button", { name: "Save" });
    expect(save).toBeDisabled();

    await user.click(within(generation).getByRole("button", { name: "Test" }));
    await waitFor(() => expect(save).toBeEnabled());
    expect(testMutate).toHaveBeenCalledWith({
      role: "generation",
      body: {
        provider: null,
        model: "anthropic/claude-haiku-4.5",
        base_url: null,
        api_key: null,
        clear_api_key: false,
      },
    });

    // Changing a value after the test invalidates it.
    await user.type(within(generation).getByLabelText("API key"), "sk-new");
    expect(save).toBeDisabled();
    await user.clear(within(generation).getByLabelText("API key"));
    expect(save).toBeEnabled();

    await user.click(save);
    await waitFor(() =>
      expect(saveMutate).toHaveBeenCalledWith({
        role: "generation",
        body: expect.objectContaining({ model: "anthropic/claude-haiku-4.5", test_token: "tok" }),
      }),
    );
  });

  it("shows the provider's error when a test fails, and keeps Save disabled", async () => {
    testMutate.mockResolvedValue({ ok: false, error: "HTTP 401: bad key", test_token: null });
    const user = userEvent.setup();
    render(<SettingsScreen />);
    const judges = section("Judges");

    await user.click(within(judges).getByRole("button", { name: "Edit" }));
    await user.click(within(judges).getByRole("button", { name: "Test" }));

    expect(await within(judges).findByText("HTTP 401: bad key")).toBeInTheDocument();
    expect(within(judges).getByRole("button", { name: "Save" })).toBeDisabled();
  });

  it("shows an embedding switch in progress and blocks editing until it ends", () => {
    state.switch = {
      job_id: "job-3",
      model: "openai/text-embedding-3-large",
      status: "running",
      done: 64,
      total: 174,
      error: null,
    };
    render(<SettingsScreen />);
    const embeddings = section("Embeddings");

    expect(within(embeddings).getByText(/re-embedded 64 \/ 174 chunks/)).toBeInTheDocument();
    expect(within(embeddings).getByRole("button", { name: "Edit" })).toBeDisabled();
  });

  it("is read-only for an account that is not an admin", () => {
    state.canEdit = false;
    render(<SettingsScreen />);

    expect(screen.getByText("Only an admin can change these")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
  });

  it("switches the route to Azure, and offers it only once .env configures it", async () => {
    const user = userEvent.setup();
    const { unmount } = render(<SettingsScreen />);
    const route = within(section("Route")).getByRole("group", { name: "Route" });

    expect(within(route).getByRole("button", { name: "OpenRouter" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await user.click(within(route).getByRole("button", { name: "Azure" }));
    expect(routeMutate).toHaveBeenCalledWith("azure");
    unmount();

    state.azureConfigured = false;
    render(<SettingsScreen />);
    expect(screen.getByRole("button", { name: "Azure" })).toBeDisabled();
  });
});
