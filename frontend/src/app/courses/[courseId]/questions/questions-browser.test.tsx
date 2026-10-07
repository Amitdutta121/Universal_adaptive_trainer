import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NuqsTestingAdapter } from "nuqs/adapters/testing";
import { beforeEach, describe, expect, it, vi } from "vitest";

const useQuestions = vi.fn();

vi.mock("@/lib/api/queries", () => ({
  useCourse: () => ({ data: { subject: "python" } }),
  useAssessmentCatalog: () => ({ data: { subjects: [] } }),
  useApprovedCurriculum: () => ({
    data: {
      version: { id: 7 },
      // Out of order on purpose: the menu follows the taxonomy's position.
      topics: [
        { id: 12, name: "Loops and iteration", position: 1 },
        { id: 11, name: "Variables", position: 0 },
        { id: 13, name: "Functions", position: 2 },
      ],
    },
  }),
  useQuestions: (params: unknown) => useQuestions(params),
}));
vi.mock("@/components/page-header", () => ({ PageHeader: () => <h1>Questions</h1> }));
vi.mock("@/components/start-card", () => ({ StartCard: () => null }));
vi.mock("@/components/course-link", () => ({
  CourseLink: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
}));
vi.mock("@/lib/use-course", () => ({ useCourseId: () => 1 }));
vi.mock("./setup/question-setup-button", () => ({ QuestionSetupButton: () => null }));
vi.mock("./generate/single/components/question-review", () => ({ QuestionReview: () => null }));

import { QuestionsBrowser } from "./questions-browser";

const lastParams = () => useQuestions.mock.calls.at(-1)?.[0];

function renderAt(searchParams = "") {
  const onUrlUpdate = vi.fn();
  render(
    <NuqsTestingAdapter searchParams={searchParams} onUrlUpdate={onUrlUpdate}>
      <QuestionsBrowser />
    </NuqsTestingAdapter>,
  );
  return onUrlUpdate;
}

beforeEach(() => {
  useQuestions.mockReset();
  useQuestions.mockReturnValue({
    data: { questions: [], status_counts: {}, total: 0 },
    isPending: false,
    isError: false,
    error: null,
  });
});

describe("QuestionsBrowser topic filter", () => {
  it("lists the approved taxonomy's topics in order and asks for none by default", async () => {
    renderAt();
    expect(lastParams()).not.toHaveProperty("topic_id");

    await userEvent.click(screen.getByRole("button", { name: /Topic: All topics/ }));
    const items = await screen.findAllByRole("menuitemcheckbox");
    expect(items.map((item) => item.textContent)).toEqual([
      "Variables",
      "Loops and iteration",
      "Functions",
    ]);
  });

  it("keeps several topics ticked and sends all of them to the server", async () => {
    const onUrlUpdate = renderAt();

    await userEvent.click(screen.getByRole("button", { name: /Topic: All topics/ }));
    await userEvent.click(await screen.findByRole("menuitemcheckbox", { name: "Functions" }));
    // The menu stays open while ticking, so the second pick needs no reopen.
    await userEvent.click(screen.getByRole("menuitemcheckbox", { name: "Variables" }));

    // Stored in taxonomy order, whatever order they were ticked in.
    expect(lastParams()).toMatchObject({ topic_id: [11, 13], curriculum_version_id: 7 });
    expect(onUrlUpdate.mock.calls.at(-1)?.[0].queryString).toContain("topic=11,13");
    expect(screen.getByRole("menuitemcheckbox", { name: "Functions" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
  });

  it("restores a shared filtered link, names the topics, and clears from the chip", async () => {
    renderAt("?topic=12,13");

    expect(lastParams()).toMatchObject({ topic_id: [12, 13] });
    expect(screen.getByRole("button", { name: /Topic: Loops and iteration\s*\+1/ })).toBeVisible();
    const chip = screen.getByRole("button", { name: /topic\s*Loops and iteration, Functions/ });

    await userEvent.click(chip);

    expect(lastParams()).not.toHaveProperty("topic_id");
    expect(within(document.body).getByText("No filters applied.")).toBeVisible();
  });
});
