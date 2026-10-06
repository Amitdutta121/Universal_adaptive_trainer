import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StrictMode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TooltipProvider } from "@/components/ui/tooltip";

const suggestCalls = vi.hoisted(() => ({ count: 0 }));

vi.mock("next/navigation", () => ({
  useParams: () => ({ courseId: "7" }),
  useRouter: () => ({ push: vi.fn() }),
}));
vi.mock("sonner", () => ({
  toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }),
}));

function ok(data: unknown) {
  return { data, error: undefined, response: { ok: true, status: 200 } };
}

vi.mock("@/lib/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/client")>();
  return {
    ...actual,
    api: {
      GET: async (path: string) => {
        if (path === "/api/curriculum/approved") {
          return ok({
            version: { id: 3, label: "Python taxonomy" },
            topics: [
              {
                id: 1,
                name: "Control flow",
                position: 0,
                review_status: "accepted",
                subtopics: [{ id: 11, name: "Loops", position: 0, review_status: "accepted" }],
              },
            ],
          });
        }
        if (path === "/api/setup") return ok({ setup: null });
        if (path === "/api/styles") {
          return ok({
            subject: "intro_python",
            styles: [
              {
                id: "py.trace",
                subject: "intro_python",
                name: "Predict what the code prints",
                summary: "Read the code.",
                question_type: "output_prediction",
                difficulty_range: ["easy"],
                checked_by: "Runs the code",
                applies_to: [],
                examples: [
                  { prompt: "one", answer: "1", grounding: "s", lines: [], options: [] },
                  { prompt: "two", answer: "2", grounding: "s", lines: [], options: [] },
                ],
              },
            ],
          });
        }
        if (path === "/api/custom-judges") return ok({ judges: [] });
        return ok(null);
      },
      POST: async (path: string) => {
        if (path !== "/api/setup/suggest") return ok(null);
        suggestCalls.count += 1;
        await new Promise((resolve) => setTimeout(resolve, 40));
        return ok({
          curriculum_version_id: 3,
          subject: "intro_python",
          subtopics: [
            { subtopic_id: 11, style_ids: ["py.trace"], reason: "Loops are learned by tracing." },
          ],
          cell_targets: [{ subtopic_id: 11, difficulty: "easy", target: 1 }],
        });
      },
    },
  };
});

import { QuestionSetupButton } from "./question-setup-button";

describe("QuestionSetupDialog remount", () => {
  beforeEach(() => {
    suggestCalls.count = 0;
  });

  it("shows the suggestion after a strict-mode remount and asks once", async () => {
    const user = userEvent.setup();
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <StrictMode>
        <QueryClientProvider client={client}>
          <TooltipProvider>
            <QuestionSetupButton />
          </TooltipProvider>
        </QueryClientProvider>
      </StrictMode>,
    );

    await user.click(await screen.findByRole("button", { name: /set up questions/i }));

    expect(await screen.findByRole("region", { name: "Loops" })).toBeInTheDocument();
    expect(suggestCalls.count).toBe(1);
  });
});
