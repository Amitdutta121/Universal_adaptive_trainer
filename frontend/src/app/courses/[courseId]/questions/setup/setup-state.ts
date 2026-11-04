/**
 * Pure logic behind the question-setup modal (ADR-069): which styles each subtopic gets, which
 * subtopics still have none, the target totals, and the save payload.
 *
 * Three layers decide a subtopic's styles:
 * 1. course: the styles the professor keeps on for the whole course;
 * 2. fit: of those, the ones the subtopic starts with. A new setup starts from the AI's
 *    suggestion; editing a saved setup starts from what it saved and asks the AI nothing;
 * 3. subtopic overrides: optional local adds and removals.
 * Course changes reach every subtopic; a subtopic edit stays local. Only styles of a type the
 * course allows (`course.question_types`) count; a blocked type's styles stay in `courseOn`, so
 * allowing the type again brings them back.
 *
 * Storage is unchanged: the save sends each subtopic's resolved set as `approved_styles`, and an
 * existing setup is turned back into layers by `initialLayers`. Counts are passed back unchanged:
 * the suggester's for a new setup, the saved ones when editing.
 */

import { DIFFICULTIES, type Difficulty } from "@/components/question-setup/types";
import type {
  CellTarget,
  CurriculumVersionDetail,
  QuestionSetup,
  SaveSetupRequest,
  Schemas,
  SetupSuggestion,
  SubtopicStyleSuggestion,
} from "@/lib/api/types";

/** Round 1's size, sent as `SaveSetupRequest.round_size` (the backend's default). */
export const FIRST_ROUND_SIZE = 10;

/** The whole-course scope; any other scope is a subtopic id. */
export const COURSE = "course";
export type Scope = typeof COURSE | number;

/** What the layer logic needs of a library style. */
export interface LayerStyle {
  id: string;
  question_type: string;
}

/** The library and the question types the course allows. */
export interface SetupContext {
  library: readonly LayerStyle[];
  allowed: ReadonlySet<string>;
}

/** A subtopic's local edits on top of the course and the AI fit. */
export interface Override {
  added: readonly string[];
  removed: readonly string[];
}

export interface SetupLayers {
  /** Styles on for the whole course, including remembered styles of a blocked type. */
  courseOn: ReadonlySet<string>;
  overrides: Readonly<Record<number, Override>>;
  /**
   * Editing only: the styles the saved fits already account for. A course style turned on that
   * is not in it (no subtopic had it) reaches every subtopic.
   */
  baseline?: ReadonlySet<string>;
}

export interface SetupSubtopic {
  id: number;
  name: string;
  /** What the AI suggested for it; `null` when the suggestion left it out or when editing. */
  suggestion: SubtopicStyleSuggestion | null;
  /** Editing only: the styles the saved setup gave it, its fit instead of a suggestion. */
  saved?: readonly string[];
}

export interface SetupTopic {
  id: number;
  name: string;
  subtopics: SetupSubtopic[];
}

/** Subtopics the professor removed from the taxonomy are not set up. */
const LIVE_STATUSES = new Set(["proposed", "accepted", "edited"]);

/**
 * The approved taxonomy's topics and subtopics, each with the AI's suggestion for it (a new
 * setup) or the styles `current` saved for it (editing, where there is no suggestion).
 */
export function setupTopics(
  curriculum: CurriculumVersionDetail,
  suggestion: SetupSuggestion | null,
  current: QuestionSetup | null = null,
): SetupTopic[] {
  const bySubtopic = new Map(
    (suggestion?.subtopics ?? []).map((entry) => [entry.subtopic_id, entry]),
  );
  const saved = new Map(
    (current?.approved_styles ?? []).map((entry) => [entry.subtopic_id, entry.style_ids]),
  );
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
          ...(current ? { saved: saved.get(subtopic.id) ?? [] } : {}),
        })),
    }))
    .filter((topic) => topic.subtopics.length > 0);
}

/**
 * Drops suggested style ids the library does not know (after a library change), so they are
 * never preselected and saved. Returns how many were dropped.
 */
export function withKnownStyles(
  topics: readonly SetupTopic[],
  libraryIds: ReadonlySet<string>,
): { topics: SetupTopic[]; dropped: number } {
  let dropped = 0;
  const known = topics.map((topic) => ({
    ...topic,
    subtopics: topic.subtopics.map((subtopic) => {
      if (!subtopic.suggestion) return subtopic;
      const styleIds = subtopic.suggestion.style_ids.filter((id) => libraryIds.has(id));
      dropped += subtopic.suggestion.style_ids.length - styleIds.length;
      return { ...subtopic, suggestion: { ...subtopic.suggestion, style_ids: styleIds } };
    }),
  }));
  return { topics: known, dropped };
}

/** Styles on for the whole course whose type the course allows, in library order. */
export function liveCourseOn(layers: SetupLayers, context: SetupContext): Set<string> {
  return new Set(
    context.library
      .filter((style) => layers.courseOn.has(style.id) && context.allowed.has(style.question_type))
      .map((style) => style.id),
  );
}

/**
 * A subtopic's fit that the course has on, then (editing) any course style no saved fit
 * accounts for.
 */
function baseStyleIds(
  layers: SetupLayers,
  live: ReadonlySet<string>,
  subtopic: SetupSubtopic,
): string[] {
  const fit = subtopic.saved ?? subtopic.suggestion?.style_ids ?? [];
  const result = fit.filter((id) => live.has(id));
  if (layers.baseline) {
    for (const id of live) {
      if (!layers.baseline.has(id) && !result.includes(id)) result.push(id);
    }
  }
  return result;
}

/**
 * The styles a subtopic gets: its fit within the course's styles, plus its local adds, minus
 * its local removals. Fit styles first, then added ones.
 */
export function effectiveStyleIds(
  layers: SetupLayers,
  context: SetupContext,
  subtopic: SetupSubtopic,
): string[] {
  const live = liveCourseOn(layers, context);
  const override = layers.overrides[subtopic.id];
  const removed = new Set(override?.removed ?? []);
  const result = baseStyleIds(layers, live, subtopic);
  for (const id of override?.added ?? []) {
    if (live.has(id) && !result.includes(id)) result.push(id);
  }
  return result.filter((id) => !removed.has(id));
}

/** Styles on in a scope: the course's live set, or a subtopic's effective set. */
export function styleIdsIn(
  layers: SetupLayers,
  context: SetupContext,
  subtopic: SetupSubtopic | null,
): Set<string> {
  return subtopic
    ? new Set(effectiveStyleIds(layers, context, subtopic))
    : liveCourseOn(layers, context);
}

export function isCustom(layers: SetupLayers, subtopicId: number): boolean {
  const override = layers.overrides[subtopicId];
  return Boolean(override && (override.added.length > 0 || override.removed.length > 0));
}

/**
 * The starting layers. A new setup has every library style of an allowed type on and no local
 * edits. An existing setup is what it saved: the course has on every style any subtopic uses,
 * each subtopic's saved styles are its fit (`setupTopics` with `current`), so nothing starts
 * local, and `baseline` lets a course style no subtopic had reach them all.
 */
export function initialLayers(
  context: SetupContext,
  current: QuestionSetup | null,
): SetupLayers {
  if (!current) {
    return {
      courseOn: new Set(
        context.library
          .filter((style) => context.allowed.has(style.question_type))
          .map((style) => style.id),
      ),
      overrides: {},
    };
  }
  const courseOn = new Set(current.approved_styles.flatMap((entry) => entry.style_ids));
  return { courseOn, overrides: {}, baseline: new Set(courseOn) };
}

/**
 * Turn styles on or off in a scope. For the course this changes `courseOn` and so every
 * subtopic. For a subtopic it records a local add or removal; a subtopic can only turn on a style
 * the course has on.
 */
export function setStyles(
  layers: SetupLayers,
  context: SetupContext,
  scope: SetupSubtopic | typeof COURSE,
  styleIds: readonly string[],
  on: boolean,
): SetupLayers {
  if (scope === COURSE) {
    const courseOn = new Set(layers.courseOn);
    for (const id of styleIds) {
      if (on) courseOn.add(id);
      else courseOn.delete(id);
    }
    return { ...layers, courseOn };
  }
  const live = liveCourseOn(layers, context);
  const base = new Set(baseStyleIds(layers, live, scope));
  const current = layers.overrides[scope.id];
  const added = new Set(current?.added ?? []);
  const removed = new Set(current?.removed ?? []);
  for (const id of styleIds) {
    if (on) {
      if (!live.has(id)) continue;
      removed.delete(id);
      if (!base.has(id)) added.add(id);
    } else {
      added.delete(id);
      if (base.has(id)) removed.add(id);
    }
  }
  const { [scope.id]: _dropped, ...rest } = layers.overrides;
  const overrides =
    added.size > 0 || removed.size > 0
      ? { ...rest, [scope.id]: { added: [...added], removed: [...removed] } }
      : rest;
  return { ...layers, overrides };
}

/** Drop a subtopic's local edits, so it follows the course again. */
export function resetSubtopic(layers: SetupLayers, subtopicId: number): SetupLayers {
  const { [subtopicId]: _dropped, ...rest } = layers.overrides;
  return { ...layers, overrides: rest };
}

/** Subtopics with no style. Approve is blocked while any remain. */
export function subtopicsWithoutStyle(
  layers: SetupLayers,
  context: SetupContext,
  topics: readonly SetupTopic[],
): SetupSubtopic[] {
  return topics.flatMap((topic) =>
    topic.subtopics.filter((subtopic) => effectiveStyleIds(layers, context, subtopic).length === 0),
  );
}

export function saveRequest(
  curriculumVersionId: number,
  layers: SetupLayers,
  context: SetupContext,
  topics: readonly SetupTopic[],
  cellTargets: readonly CellTarget[],
): SaveSetupRequest {
  return {
    curriculum_version_id: curriculumVersionId,
    approved_styles: topics.flatMap((topic) =>
      topic.subtopics.map((subtopic) => ({
        subtopic_id: subtopic.id,
        style_ids: effectiveStyleIds(layers, context, subtopic),
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

/**
 * Difficulties the AI set a target for that none of the selected styles can be written at, so
 * no question would be generated for that cell.
 */
export function uncoveredDifficulties(
  selected: readonly { difficulty_range: readonly Difficulty[] }[],
  row: Record<Difficulty, number | null> | undefined,
): Difficulty[] {
  const covered = new Set(selected.flatMap((style) => style.difficulty_range));
  return DIFFICULTIES.filter(
    (difficulty) => (row?.[difficulty] ?? 0) > 0 && !covered.has(difficulty),
  );
}

export function rowTotal(row: Record<Difficulty, number | null> | undefined): number {
  if (!row) return 0;
  return DIFFICULTIES.reduce((sum, difficulty) => sum + (row[difficulty] ?? 0), 0);
}

// ------------------------------------------------ existing questions (ADR-070)

export type QuestionVisibility = Schemas["QuestionVisibilityResponse"];

/**
 * Approved and hidden questions written in these styles, in a scope: the whole course, or the
 * questions tagged with one subtopic.
 */
export function questionsIn(
  visibility: QuestionVisibility,
  scope: Scope,
  styleIds: readonly string[],
): { approved: number; hidden: number } {
  const ids = new Set(styleIds);
  const rows =
    scope === COURSE
      ? visibility.by_style.filter((row) => ids.has(row.style_id))
      : visibility.by_cell.filter(
          (row) => row.subtopic_id === scope && row.style_id !== null && ids.has(row.style_id),
        );
  return {
    approved: rows.reduce((sum, row) => sum + row.approved, 0),
    hidden: rows.reduce((sum, row) => sum + row.hidden, 0),
  };
}

/**
 * Subtopic x difficulty cells in the scope that meet their target now and would fall below it
 * if the approved questions in these styles were hidden.
 */
export function slotsBelowTarget(
  visibility: QuestionVisibility,
  cellTargets: readonly CellTarget[],
  scope: Scope,
  styleIds: readonly string[],
): number {
  const ids = new Set(styleIds);
  let slots = 0;
  for (const cell of cellTargets) {
    if (cell.target <= 0 || (scope !== COURSE && cell.subtopic_id !== scope)) continue;
    const rows = visibility.by_cell.filter(
      (row) => row.subtopic_id === cell.subtopic_id && row.difficulty === cell.difficulty,
    );
    const now = rows.reduce((sum, row) => sum + row.approved, 0);
    const hiding = rows
      .filter((row) => row.style_id !== null && ids.has(row.style_id))
      .reduce((sum, row) => sum + row.approved, 0);
    if (now >= cell.target && now - hiding < cell.target) slots++;
  }
  return slots;
}
