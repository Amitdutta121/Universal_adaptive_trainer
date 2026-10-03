/**
 * Pure logic behind the question-setup modal: which styles the professor approved for each
 * subtopic, which subtopics still have none, the target totals, and the save payload.
 *
 * A suggested style is undecided until the professor uses or skips it; a style added from the
 * library is approved by adding it. Counts are the suggester's and are passed back unchanged.
 */

import { DIFFICULTIES, type Difficulty } from "@/components/question-setup/types";
import type {
  CellTarget,
  CurriculumVersionDetail,
  QuestionSetup,
  SaveSetupRequest,
  SetupSuggestion,
  SubtopicStyleSuggestion,
} from "@/lib/api/types";

/** Round 1's size, sent as `SaveSetupRequest.round_size` (the backend's default). */
export const FIRST_ROUND_SIZE = 10;

export type Verdict = "approved" | "skipped";

export interface SetupChoices {
  /** Use / skip per suggested style, keyed by subtopic id then style id. */
  verdicts: Readonly<Record<number, Readonly<Record<string, Verdict>>>>;
  /** Styles the professor added from the library, per subtopic. Always approved. */
  added: Readonly<Record<number, readonly string[]>>;
}

export interface SetupSubtopic {
  id: number;
  name: string;
  /** What the AI suggested for it; `null` when the suggestion left it out. */
  suggestion: SubtopicStyleSuggestion | null;
}

export interface SetupTopic {
  id: number;
  name: string;
  subtopics: SetupSubtopic[];
}

/** Subtopics the professor removed from the taxonomy are not set up. */
const LIVE_STATUSES = new Set(["proposed", "accepted", "edited"]);

/** The approved taxonomy's topics and subtopics, each with the AI's suggestion for it. */
export function setupTopics(
  curriculum: CurriculumVersionDetail,
  suggestion: SetupSuggestion,
): SetupTopic[] {
  const bySubtopic = new Map(suggestion.subtopics.map((entry) => [entry.subtopic_id, entry]));
  return [...curriculum.topics]
    .filter((topic) => LIVE_STATUSES.has(topic.review_status))
    .sort((a, b) => a.position - b.position)
    .map((topic) => ({
      id: topic.id,
      name: topic.name,
      subtopics: [...topic.subtopics]
        .filter((subtopic) => LIVE_STATUSES.has(subtopic.review_status))
        .sort((a, b) => a.position - b.position)
        .map((subtopic) => ({
          id: subtopic.id,
          name: subtopic.name,
          suggestion: bySubtopic.get(subtopic.id) ?? null,
        })),
    }))
    .filter((topic) => topic.subtopics.length > 0);
}

/**
 * The starting choices. Editing an existing setup starts from what was approved last time: a
 * previously approved style the AI suggests again is pre-approved, one it no longer suggests is
 * kept as an added style.
 */
export function initialChoices(
  topics: readonly SetupTopic[],
  current: QuestionSetup | null,
): SetupChoices {
  const verdicts: Record<number, Record<string, Verdict>> = {};
  const added: Record<number, string[]> = {};
  if (!current) return { verdicts, added };
  const previous = new Map(current.approved_styles.map((entry) => [entry.subtopic_id, entry.style_ids]));
  for (const topic of topics) {
    for (const subtopic of topic.subtopics) {
      const styleIds = previous.get(subtopic.id) ?? [];
      const suggested = new Set(subtopic.suggestion?.style_ids ?? []);
      for (const styleId of styleIds) {
        if (suggested.has(styleId)) {
          verdicts[subtopic.id] = { ...verdicts[subtopic.id], [styleId]: "approved" };
        } else {
          added[subtopic.id] = [...(added[subtopic.id] ?? []), styleId];
        }
      }
    }
  }
  return { verdicts, added };
}

export function decide(
  choices: SetupChoices,
  subtopicId: number,
  styleId: string,
  verdict: Verdict,
): SetupChoices {
  return {
    ...choices,
    verdicts: {
      ...choices.verdicts,
      [subtopicId]: { ...choices.verdicts[subtopicId], [styleId]: verdict },
    },
  };
}

export function addStyle(choices: SetupChoices, subtopicId: number, styleId: string): SetupChoices {
  const current = choices.added[subtopicId] ?? [];
  if (current.includes(styleId)) return choices;
  return { ...choices, added: { ...choices.added, [subtopicId]: [...current, styleId] } };
}

export function removeStyle(choices: SetupChoices, subtopicId: number, styleId: string): SetupChoices {
  const current = choices.added[subtopicId] ?? [];
  return {
    ...choices,
    added: { ...choices.added, [subtopicId]: current.filter((id) => id !== styleId) },
  };
}

/** Approve every suggested style the professor has not decided yet; skips are kept. */
export function approveAllUndecided(choices: SetupChoices, topics: readonly SetupTopic[]): SetupChoices {
  const verdicts: Record<number, Record<string, Verdict>> = { ...choices.verdicts };
  for (const topic of topics) {
    for (const subtopic of topic.subtopics) {
      for (const styleId of subtopic.suggestion?.style_ids ?? []) {
        if (verdicts[subtopic.id]?.[styleId]) continue;
        verdicts[subtopic.id] = { ...verdicts[subtopic.id], [styleId]: "approved" };
      }
    }
  }
  return { ...choices, verdicts };
}

/** The approved styles of one subtopic: used suggestions first, then added ones. */
export function approvedStyleIds(choices: SetupChoices, subtopic: SetupSubtopic): string[] {
  const used = (subtopic.suggestion?.style_ids ?? []).filter(
    (styleId) => choices.verdicts[subtopic.id]?.[styleId] === "approved",
  );
  const added = (choices.added[subtopic.id] ?? []).filter((styleId) => !used.includes(styleId));
  return [...used, ...added];
}

export function undecidedCount(choices: SetupChoices, topics: readonly SetupTopic[]): number {
  let count = 0;
  for (const topic of topics) {
    for (const subtopic of topic.subtopics) {
      for (const styleId of subtopic.suggestion?.style_ids ?? []) {
        if (!choices.verdicts[subtopic.id]?.[styleId]) count += 1;
      }
    }
  }
  return count;
}

/** Subtopics with no approved style. Approve is blocked while any remain. */
export function subtopicsWithoutStyle(
  choices: SetupChoices,
  topics: readonly SetupTopic[],
): SetupSubtopic[] {
  return topics.flatMap((topic) =>
    topic.subtopics.filter((subtopic) => approvedStyleIds(choices, subtopic).length === 0),
  );
}

export function saveRequest(
  curriculumVersionId: number,
  choices: SetupChoices,
  topics: readonly SetupTopic[],
  cellTargets: readonly CellTarget[],
): SaveSetupRequest {
  return {
    curriculum_version_id: curriculumVersionId,
    approved_styles: topics.flatMap((topic) =>
      topic.subtopics.map((subtopic) => ({
        subtopic_id: subtopic.id,
        style_ids: approvedStyleIds(choices, subtopic),
      })),
    ),
    cell_targets: [...cellTargets],
    round_size: FIRST_ROUND_SIZE,
  };
}

/** Targets per subtopic x difficulty, as the AI set them; `null` where it set none. */
export function targetsBySubtopic(
  cellTargets: readonly CellTarget[],
): Map<number, Record<Difficulty, number | null>> {
  const bySubtopic = new Map<number, Record<Difficulty, number | null>>();
  for (const cell of cellTargets) {
    const row = bySubtopic.get(cell.subtopic_id) ?? { easy: null, medium: null, hard: null };
    row[cell.difficulty] = cell.target;
    bySubtopic.set(cell.subtopic_id, row);
  }
  return bySubtopic;
}

export function rowTotal(row: Record<Difficulty, number | null> | undefined): number {
  if (!row) return 0;
  return DIFFICULTIES.reduce((sum, difficulty) => sum + (row[difficulty] ?? 0), 0);
}
