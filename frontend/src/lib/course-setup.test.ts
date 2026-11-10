import { describe, expect, it } from "vitest";
import type { Schemas } from "@/lib/api/types";
import { deriveSetup, type SetupInputs } from "./course-setup";

const book = (id: number, title: string) => ({ id, title }) as Schemas["BookSummary"];
const version = (id: number, status: string, label = `v${id}`) =>
  ({ id, status, label }) as Schemas["CurriculumVersionSummary"];
const approved = (id = 7) =>
  ({
    version: version(id, "approved", "Intro to Python"),
    topic_count: 8,
    subtopic_count: 31,
  }) as Schemas["CurriculumVersionDetail"];
const round = (status: string, produced = 0, extra = {}) =>
  ({
    id: 3,
    number: 1,
    status,
    produced,
    requested: 10,
    error: null,
    ...extra,
  }) as Schemas["GenerationRoundOut"];
const setupRow = (latest: Schemas["GenerationRoundOut"] | null = null) =>
  ({
    id: 1,
    approved_styles: [
      { subtopic_id: 1, style_ids: ["py.predict_output", "py.trace_steps"] },
      { subtopic_id: 2, style_ids: ["py.predict_output"] },
    ],
    cell_targets: [
      { subtopic_id: 1, difficulty: "easy", target: 4 },
      { subtopic_id: 2, difficulty: "easy", target: 2 },
    ],
    latest_round: latest,
  }) as unknown as Schemas["QuestionSetupOut"];
const link = (approvedCount: number, live = false) =>
  ({
    curriculum_version_id: 7,
    approved_question_count: approvedCount,
    classroom: live ? { id: 40 } : null,
  }) as Schemas["TaxonomyLinkOut"];

function inputs(overrides: Partial<SetupInputs> = {}): SetupInputs {
  return {
    books: { books: [], total: 0 },
    versions: { versions: [] } as unknown as Schemas["CurriculumListResponse"],
    approved: null,
    setup: null,
    link: null,
    recipes: undefined,
    ...overrides,
  };
}

const states = (input: SetupInputs) =>
  Object.fromEntries(deriveSetup(input).steps.map((step) => [step.key, step.state]));

describe("deriveSetup", () => {
  it("starts a new course on content, with the dependent steps blocked", () => {
    const result = deriveSetup(inputs());
    expect(states(inputs())).toEqual({
      content: "next",
      curriculum: "todo",
      questions: "blocked",
      review: "blocked",
      tutorials: "blocked",
      share: "blocked",
    });
    expect(result.done).toBe(0);
    expect(result.live).toBe(false);
  });

  it("lets a professor import a curriculum without uploading content", () => {
    const result = deriveSetup(inputs({ approved: approved() }));
    expect(result.steps[1].state).toBe("done");
    // Content is still the next required step; question types is open now.
    expect(result.next?.key).toBe("content");
    expect(result.steps[2].state).toBe("todo");
  });

  it("points at a waiting draft rather than asking for a new curriculum", () => {
    const result = deriveSetup(
      inputs({
        books: { books: [book(1, "Agah")], total: 1 },
        versions: {
          versions: [version(2, "proposed", "Draft from Agah")],
        } as unknown as Schemas["CurriculumListResponse"],
      }),
    );
    expect(result.next?.key).toBe("curriculum");
    expect(result.next?.detail).toContain('Draft "Draft from Agah"');
    expect(result.next?.action).toBe("Review the draft");
  });

  it("shows round 1 writing questions as running, then review as next", () => {
    const base = { books: { books: [book(1, "Agah")], total: 1 }, approved: approved() };
    const running = deriveSetup(inputs({ ...base, setup: setupRow(round("running", 4)) }));
    expect(running.steps[2].detail).toBe("2 question styles · 6 target questions");
    expect(running.next?.key).toBe("review");
    expect(running.next?.state).toBe("running");
    expect(running.next?.detail).toBe("Round 1 is writing questions: 4 of 10");

    const done = deriveSetup(inputs({ ...base, setup: setupRow(round("done", 10)) }));
    expect(done.next?.state).toBe("next");
    expect(done.next?.detail).toBe("Approve at least one question in the Review Queue");
  });

  it("says why when round 1 failed", () => {
    const result = deriveSetup(
      inputs({
        approved: approved(),
        setup: setupRow(round("failed", 0, { error: "No model configured" })),
      }),
    );
    expect(result.steps[3].detail).toBe("Round 1 failed: No model configured");
  });

  it("counts an approved question as reviewed even without a setup (manual generation)", () => {
    const result = deriveSetup(inputs({ approved: approved(), link: link(3) }));
    expect(result.steps[3].state).toBe("done");
    expect(result.steps[5].state).toBe("todo");
    expect(result.steps[5].detail).toBe("Create the link for 3 approved questions");
  });

  it("blocks sharing until a question is approved, as the backend refuses an empty set", () => {
    const result = deriveSetup(
      inputs({ approved: approved(), setup: setupRow(round("done", 10)), link: link(0) }),
    );
    expect(result.steps[5].state).toBe("blocked");
    expect(result.steps[5].detail).toBe("Needs at least one approved question");
  });

  it("treats tutorials as optional: never the next step, counted once decided", () => {
    const base = {
      books: { books: [book(1, "Agah")], total: 1 },
      approved: approved(),
      setup: setupRow(round("done", 10)),
      link: link(5),
    };
    const undecided = deriveSetup(
      inputs({
        ...base,
        recipes: {
          recipes: [{}, {}],
          decisions: {},
          live: true,
        } as unknown as Schemas["TutorialRecipeListResponse"],
      }),
    );
    expect(undecided.steps[4].state).toBe("optional");
    expect(undecided.steps[4].detail).toContain("live tutorials");
    expect(undecided.next?.key).toBe("share");
    expect(undecided.done).toBe(4);

    const decided = deriveSetup(
      inputs({
        ...base,
        recipes: {
          recipes: [{}, {}],
          decisions: { worked: true },
          live: true,
        } as unknown as Schemas["TutorialRecipeListResponse"],
      }),
    );
    expect(decided.steps[4].state).toBe("done");
    // Optional: deciding does not change the required count.
    expect(decided.done).toBe(4);
    expect(decided.total).toBe(5);
  });

  it("is live once the link exists, with no next step left", () => {
    const result = deriveSetup(
      inputs({
        books: { books: [book(1, "Agah")], total: 1 },
        approved: approved(),
        setup: setupRow(round("done", 10)),
        link: link(5, true),
      }),
    );
    expect(result.live).toBe(true);
    expect(result.next).toBeNull();
    expect(result.curriculumVersionId).toBe(7);
  });

  it("keeps the link live but flags review when every approved question was later rejected", () => {
    const result = deriveSetup(
      inputs({
        books: { books: [book(1, "Agah")], total: 1 },
        approved: approved(),
        setup: setupRow(round("done", 10)),
        link: link(0, true),
      }),
    );
    expect(result.live).toBe(true);
    expect(result.steps[5].state).toBe("done");
    expect(result.next?.key).toBe("review");
  });

  it("lists at most two content titles", () => {
    const result = deriveSetup(
      inputs({ books: { books: [book(1, "A"), book(2, "B"), book(3, "C")], total: 3 } }),
    );
    expect(result.steps[0].detail).toBe("3 items: A, B, …");
  });

  it("shows a book import that is still running, and why one failed", () => {
    const job = (status: string, error: string | null = null) =>
      ({
        kind: "book_import",
        title: "Import book · agah.pdf",
        status,
        error,
      }) as Schemas["JobOut"];
    const running = deriveSetup(inputs({ imports: [job("running")] }));
    expect(running.steps[0].state).toBe("running");
    expect(running.steps[0].detail).toBe("Importing agah.pdf");

    const failed = deriveSetup(inputs({ imports: [job("failed", "No text could be read")] }));
    expect(failed.steps[0].state).toBe("next");
    expect(failed.steps[0].detail).toBe("Import failed: No text could be read");

    const more = deriveSetup(
      inputs({ books: { books: [book(1, "A")], total: 1 }, imports: [job("queued")] }),
    );
    expect(more.steps[0].state).toBe("done");
    expect(more.steps[0].detail).toBe("1 item: A · importing 1 more");
  });

  it("names other taxonomies whose links still serve students", () => {
    const old = {
      curriculum_version_id: 3,
      label: "Module 1",
      approved_question_count: 4,
      classroom: { id: 9 },
    } as Schemas["TaxonomyLinkOut"];
    const result = deriveSetup(
      inputs({ approved: approved(7), link: link(0), allLinks: [old, link(0)] }),
    );
    expect(result.live).toBe(false);
    expect(result.otherLive).toEqual([{ curriculumVersionId: 3, label: "Module 1" }]);
  });

  it("says when the course's subject has no question styles, instead of offering setup", () => {
    const result = deriveSetup(inputs({ approved: approved(), subjectWithoutStyles: "Physics" }));
    expect(result.steps[2].state).toBe("blocked");
    expect(result.steps[2].detail).toBe("No question styles for Physics yet; the assistant can draft them");
  });
});
