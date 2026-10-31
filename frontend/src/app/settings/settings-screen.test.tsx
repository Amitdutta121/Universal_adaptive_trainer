import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SettingsScreen } from "./settings-screen";

const testMutate = vi.fn();
const saveMutate = vi.fn();
const resetMutate = vi.fn();
const routeMutate = vi.fn();
const providerSaveMutate = vi.fn();
const themeSet = vi.fn();
const state = vi.hoisted(() => ({
  canEdit: true,
  switch: null as unknown,
  azureConfigured: true,
}));

vi.mock("@/components/page-header", () => ({
  PageHeader: ({ title }: { title: string }) => <h1>{title}</h1>,
}));

function provider(id: string, label: string, overrides: Record<string, unknown> = {}) {
  return {
    id,
    label,
    base_url: null,
    base_url_required: false,
    api_key_masked: "••••1234",
    chat_model: null,
    embedding_model: null,
    embeds: false,
    lists_models: true,
    configured: true,
    saved: [],
    ...overrides,
  };
}

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
      providers: [
        provider("openrouter", "OpenRouter", {
          chat_model: "deepseek/deepseek-chat",
          embedding_model: "openai/text-embedding-3-small",
          embeds: true,
        }),
        provider("azure", "Azure OpenAI", {
          base_url_required: true,
          lists_models: false,
          configured: state.azureConfigured,
          api_key_masked: state.azureConfigured ? "••••5678" : null,
          embeds: true,
        }),
        provider("anthropic", "Anthropic (Claude)", { chat_model: "claude-haiku-4-5" }),
        provider("deepseek", "DeepSeek", { configured: false, api_key_masked: null }),
      ],
      route: "openrouter",
      route_source: "env",
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
  useProviderModels: () => ({
    data: [
      {
        id: "anthropic/claude-haiku-4.5",
        name: "Anthropic: Claude Haiku 4.5",
        context_length: 200000,
        prompt_price: 1,
        completion_price: 5,
      },
      {
        id: "openai/gpt-4o",
        name: "OpenAI: GPT-4o",
        context_length: 128000,
        prompt_price: 2.5,
        completion_price: 10,
      },
    ],
    isFetching: false,
    isError: false,
  }),
  useTestRoleSettings: () => ({ mutateAsync: testMutate, isPending: false, error: null }),
  useSaveRoleSettings: () => ({ mutateAsync: saveMutate, isPending: false, error: null }),
  useResetRoleSettings: () => ({ mutate: resetMutate, isPending: false }),
  useSetRoute: () => ({ mutate: routeMutate, isPending: false, error: null }),
  useSaveProvider: () => ({
    mutate: providerSaveMutate,
    isPending: false,
    error: null,
    reset: vi.fn(),
  }),
  useResetProvider: () => ({ mutate: vi.fn(), isPending: false, error: null }),
}));

vi.mock("next-themes", () => ({ useTheme: () => ({ theme: "system", setTheme: themeSet }) }));

async function openCategory(user: ReturnType<typeof userEvent.setup>, name: string) {
  await user.click(screen.getByRole("tab", { name }));
}

function section(name: string): HTMLElement {
  const heading = screen.getByRole("heading", { name: new RegExp(`^${name}`) });
  return heading.closest("section") as HTMLElement;
}

beforeEach(() => {
  testMutate.mockReset();
  saveMutate.mockReset();
  routeMutate.mockReset();
  providerSaveMutate.mockReset();
  state.canEdit = true;
  state.switch = null;
  state.azureConfigured = true;
});

describe("SettingsScreen", () => {
  it("picks a model from the list, tests it, then saves with the test's token", async () => {
    testMutate.mockResolvedValue({ ok: true, error: null, dimension: null, test_token: "tok" });
    saveMutate.mockResolvedValue({});
    const user = userEvent.setup();
    render(<SettingsScreen />);
    await openCategory(user, "Question authoring");
    const generation = section("Generation");

    await user.click(within(generation).getByRole("combobox", { name: "Model" }));
    await user.type(screen.getByPlaceholderText(/Search models/), "haiku");
    // The list shows each model's context window and price per million tokens.
    const option = screen.getByRole("option", { name: /Claude Haiku 4\.5/ });
    expect(option).toHaveTextContent("200K");
    expect(option).toHaveTextContent("$1 / $5");
    await user.click(option);

    expect(within(generation).getByText(/Switch to/)).toHaveTextContent(
      "anthropic/claude-haiku-4.5",
    );
    await user.click(within(generation).getByRole("button", { name: "Test and save" }));

    await waitFor(() =>
      expect(saveMutate).toHaveBeenCalledWith({
        role: "generation",
        body: expect.objectContaining({ model: "anthropic/claude-haiku-4.5", test_token: "tok" }),
      }),
    );
    expect(testMutate).toHaveBeenCalledWith({
      role: "generation",
      body: {
        provider: null,
        model: "anthropic/claude-haiku-4.5",
        base_url: null,
        api_key: null,
        clear_api_key: true,
      },
    });
  });

  it("accepts a model id that is not listed", async () => {
    const user = userEvent.setup();
    render(<SettingsScreen />);
    await openCategory(user, "Question authoring");
    const judges = section("Judges");

    await user.click(within(judges).getByRole("combobox", { name: "Model" }));
    await user.type(screen.getByPlaceholderText(/Search models/), "acme/private-model");
    await user.click(screen.getByRole("option", { name: /Use acme\/private-model/ }));

    expect(within(judges).getByText(/Switch to/)).toHaveTextContent("acme/private-model");
  });

  it("shows the provider's error when a test fails, and saves nothing", async () => {
    testMutate.mockResolvedValue({ ok: false, error: "HTTP 401: bad key", test_token: null });
    const user = userEvent.setup();
    render(<SettingsScreen />);
    await openCategory(user, "Question authoring");
    const judges = section("Judges");

    await user.click(within(judges).getByRole("combobox", { name: "Model" }));
    await user.click(screen.getByRole("option", { name: /GPT-4o/ }));
    await user.click(within(judges).getByRole("button", { name: "Test and save" }));

    expect(await within(judges).findByText("HTTP 401: bad key")).toBeInTheDocument();
    expect(testMutate).toHaveBeenCalledWith({
      role: "judges",
      body: expect.objectContaining({ model: "openai/gpt-4o" }),
    });
    expect(saveMutate).not.toHaveBeenCalled();

    // Discard drops the change and the failure with it.
    await user.click(within(judges).getByRole("button", { name: "Discard" }));
    expect(within(judges).queryByText("HTTP 401: bad key")).not.toBeInTheDocument();
    expect(within(judges).queryByRole("button", { name: "Test and save" })).not.toBeInTheDocument();
  });

  it("shows an embedding switch in progress and blocks changes until it ends", async () => {
    state.switch = {
      job_id: "job-3",
      model: "openai/text-embedding-3-large",
      status: "running",
      done: 64,
      total: 174,
      error: null,
    };
    const user = userEvent.setup();
    render(<SettingsScreen />);
    await openCategory(user, "Content & retrieval");
    const embeddings = section("Embeddings");

    expect(within(embeddings).getByText(/re-embedded 64 \/ 174 chunks/)).toBeInTheDocument();
    expect(within(embeddings).getByRole("combobox", { name: "Model" })).toBeDisabled();
  });

  it("is read-only for an account that is not an admin", async () => {
    state.canEdit = false;
    const user = userEvent.setup();
    render(<SettingsScreen />);
    await openCategory(user, "Question authoring");

    expect(screen.getByText("Only an admin can change these")).toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: "Model" })).not.toBeInTheDocument();
    expect(within(section("Generation")).getByText(/deepseek\/deepseek-chat/)).toBeInTheDocument();
  });

  it("sets the default provider, offering only providers that are set up", async () => {
    const user = userEvent.setup();
    render(<SettingsScreen />);

    await user.click(screen.getByRole("combobox", { name: "Default provider" }));
    expect(screen.getByRole("option", { name: /DeepSeek \(not set up\)/ })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    await user.click(screen.getByRole("option", { name: "Azure OpenAI" }));
    expect(routeMutate).toHaveBeenCalledWith("azure");
  });

  it("tests and saves a provider's key from the Providers pane", async () => {
    const user = userEvent.setup();
    render(<SettingsScreen />);
    const anthropic = section("Anthropic");

    await user.click(within(anthropic).getByRole("button", { name: "Edit" }));
    await user.type(within(anthropic).getByLabelText("API key"), "sk-ant");
    await user.click(within(anthropic).getByRole("button", { name: "Test and save" }));

    expect(providerSaveMutate).toHaveBeenCalledWith(
      { provider: "anthropic", body: { base_url: null, api_key: "sk-ant", chat_model: null } },
      expect.anything(),
    );
  });

  it("moves one role onto another provider and its default model", async () => {
    testMutate.mockResolvedValue({ ok: true, error: null, dimension: null, test_token: "tok" });
    saveMutate.mockResolvedValue({});
    const user = userEvent.setup();
    render(<SettingsScreen />);
    await openCategory(user, "Question authoring");
    const judges = section("Judges");

    await user.click(within(judges).getByRole("combobox", { name: "Provider" }));
    // Only providers that are set up are offered.
    expect(screen.queryByRole("option", { name: "DeepSeek" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("option", { name: "Anthropic (Claude)" }));

    expect(within(judges).getByText(/Switch to/)).toHaveTextContent(
      "Anthropic (Claude) · claude-haiku-4-5",
    );
    await user.click(within(judges).getByRole("button", { name: "Test and save" }));
    expect(testMutate).toHaveBeenCalledWith({
      role: "judges",
      body: expect.objectContaining({ provider: "anthropic", model: null }),
    });
  });

  it("offers embeddings only providers that can embed", async () => {
    const user = userEvent.setup();
    render(<SettingsScreen />);
    await openCategory(user, "Content & retrieval");

    await user.click(within(section("Embeddings")).getByRole("combobox", { name: "Provider" }));
    expect(screen.getByRole("option", { name: "Azure OpenAI" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "Anthropic (Claude)" })).not.toBeInTheDocument();
  });

  it("groups the settings into categories and shows one category at a time", async () => {
    const user = userEvent.setup();
    render(<SettingsScreen />);

    // Providers opens first: the default provider, and no model roles.
    expect(screen.getByRole("tab", { name: "Providers" })).toHaveAttribute("aria-selected", "true");
    expect(section("Default provider")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /^Generation/ })).not.toBeInTheDocument();

    await openCategory(user, "Assistants");
    for (const name of ["Professor agent", "Tutorials", "Ask why"]) {
      expect(section(name)).toBeInTheDocument();
    }
    expect(screen.queryByRole("heading", { name: /^Default provider/ })).not.toBeInTheDocument();

    await openCategory(user, "Appearance");
    await user.click(screen.getByRole("button", { name: "Dark" }));
    expect(themeSet).toHaveBeenCalledWith("dark");
  });
});
