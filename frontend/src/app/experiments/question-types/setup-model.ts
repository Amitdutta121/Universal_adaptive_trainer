/**
 * State and rules for the type-first question setup.
 *
 * A new course starts with its subject's default question types allowed
 * (`default_types_for`, app/assessment/catalog.py) and, for Intro Python, that is every type.
 * Course Settings can block a type later; setup still lists it, greyed, with "Allow".
 *
 * Three layers decide which styles a subtopic gets:
 * 1. course: the styles the professor keeps on for the whole course (all on at the start);
 * 2. AI fit: of those, the ones the suggester attaches to each subtopic;
 * 3. subtopic overrides: optional local adds and removals.
 * Course changes reach every subtopic; a subtopic edit stays local. A style of a blocked type is
 * off everywhere but remembered, so allowing the type again brings it back.
 *
 * TODO(real): `aiFit` mirrors the suggester's fallback ranking (`_rank_by_fit` + difficulty
 * fill in app/styles/library.py), not its LLM picks; `existingCount` and `targetsFor` stand in
 * for `QuestionRow.style_id` counts and the suggestion's `cell_targets`.
 */

import type { Difficulty, ExampleQuestion, Subtopic, Topic } from "../question-setup/mock-types";
import { DIFFICULTIES } from "../question-setup/mock-types";

export const COURSE = "course";
/** `COURSE` or a subtopic id. */
export type Scope = string;

/** One style from the subject's library (`styles/<subject>/*.yaml`). */
export interface LibraryStyle {
  id: string;
  name: string;
  summary: string;
  questionType: string;
  difficulties: Difficulty[];
  checkedBy: string;
  appliesTo: string[];
  examples: ExampleQuestion[];
}

export interface Course {
  name: string;
  taxonomyLabel: string;
  /** The subject's question types, in catalogue order, with display labels. */
  questionTypes: Record<string, string>;
  library: readonly LibraryStyle[];
  topics: readonly Topic[];
}

export interface TypeGroup {
  id: string;
  label: string;
  styles: LibraryStyle[];
}

export interface Override {
  added: ReadonlySet<string>;
  removed: ReadonlySet<string>;
}

export interface SetupState {
  /** Question type ids the course allows (course Settings). */
  allowed: ReadonlySet<string>;
  courseOn: ReadonlySet<string>;
  overrides: Readonly<Record<string, Override>>;
  /** `${scope}|${styleId}` -> hidden question count. */
  hidden: Readonly<Record<string, number>>;
}

export interface SubtopicRef {
  topicId: string;
  topicName: string;
  subtopic: Subtopic;
}

/** Mirrors `MAX_STYLES_PER_SUBTOPIC` in app/styles/library.py. */
const MAX_STYLES_PER_SUBTOPIC = 4;

function hash(text: string): number {
  let value = 0;
  for (let index = 0; index < text.length; index++) {
    value = (value * 31 + text.charCodeAt(index)) >>> 0;
  }
  return value;
}

export function covers(style: LibraryStyle, difficulty: Difficulty): boolean {
  return style.difficulties.includes(difficulty);
}

export function typeGroups(course: Course): TypeGroup[] {
  return Object.entries(course.questionTypes).map(([id, label]) => ({
    id,
    label,
    styles: course.library.filter((style) => style.questionType === id),
  }));
}

export function subtopics(course: Course): SubtopicRef[] {
  return course.topics.flatMap((topic) =>
    topic.subtopics.map((subtopic) => ({ topicId: topic.id, topicName: topic.name, subtopic })),
  );
}

/** A new course: every subject type allowed, every library style on, nothing local. */
export function initialState(course: Course): SetupState {
  return {
    allowed: new Set(Object.keys(course.questionTypes)),
    courseOn: new Set(course.library.map((style) => style.id)),
    overrides: {},
    hidden: {},
  };
}

export function typeAllowed(state: SetupState, typeId: string): boolean {
  return state.allowed.has(typeId);
}

/** The course's styles that are on and whose type the course allows. */
export function liveCourseOn(state: SetupState, course: Course): Set<string> {
  return new Set(
    course.library
      .filter((style) => state.courseOn.has(style.id) && typeAllowed(state, style.questionType))
      .map((style) => style.id),
  );
}

export function setAllowed(state: SetupState, typeId: string, allowed: boolean): SetupState {
  const next = new Set(state.allowed);
  if (allowed) next.add(typeId);
  else next.delete(typeId);
  return { ...state, allowed: next };
}

const WORD = /[a-z]+/g;
function words(text: string): Set<string> {
  return new Set(
    (text.toLowerCase().match(WORD) ?? [])
      .filter((w) => w.length > 2)
      .map((w) => w.replace(/s+$/, "")),
  );
}

/**
 * Styles the suggester would attach to this subtopic: the best `applies_to` matches, up to
 * the cap, plus one fitting style for each planned difficulty nothing covers yet.
 */
export function aiFit(course: Course, ref: SubtopicRef): Set<string> {
  const target = words(`${ref.subtopic.name} ${ref.topicName}`);
  const overlap = (style: LibraryStyle) =>
    [...words(style.appliesTo.join(" "))].filter((w) => target.has(w)).length;
  const ranked = [...course.library].sort((a, b) => overlap(b) - overlap(a));
  const chosen = ranked.filter((style) => overlap(style) > 0).slice(0, MAX_STYLES_PER_SUBTOPIC);
  if (chosen.length === 0 && ranked[0]) chosen.push(ranked[0]);
  const targets = targetsFor(ref.subtopic);
  for (const difficulty of DIFFICULTIES) {
    if (targets[difficulty] === 0 || chosen.some((style) => covers(style, difficulty))) continue;
    const fit = ranked.find((style) => covers(style, difficulty));
    if (fit) chosen.push(fit);
  }
  return new Set(chosen.map((style) => style.id));
}

export function effective(state: SetupState, course: Course, ref: SubtopicRef): Set<string> {
  const override = state.overrides[ref.subtopic.id];
  const live = liveCourseOn(state, course);
  const result = new Set<string>();
  for (const id of aiFit(course, ref)) if (live.has(id)) result.add(id);
  for (const id of override?.added ?? []) if (live.has(id)) result.add(id);
  for (const id of override?.removed ?? []) result.delete(id);
  return result;
}

/** Styles on in a scope: the course set, or a subtopic's effective set. */
export function onIn(state: SetupState, course: Course, scope: Scope): ReadonlySet<string> {
  if (scope === COURSE) return liveCourseOn(state, course);
  const ref = subtopics(course).find((entry) => entry.subtopic.id === scope);
  return ref ? effective(state, course, ref) : new Set();
}

export function isCustom(state: SetupState, subtopicId: string): boolean {
  const override = state.overrides[subtopicId];
  return Boolean(override && (override.added.size > 0 || override.removed.size > 0));
}

/** Approved questions already written in this style, in this scope. */
export function existingCount(style: LibraryStyle, scope: Scope): number {
  if (scope === COURSE) return 6 + (hash(style.id) % 30);
  return hash(`${scope}:${style.id}`) % 5;
}

export function targetsFor(subtopic: Subtopic): Record<Difficulty, number> {
  return { easy: 3, medium: 3, hard: hash(subtopic.id) % 3 === 0 ? 0 : 1 };
}

function withOverride(
  state: SetupState,
  subtopicId: string,
  change: (added: Set<string>, removed: Set<string>) => void,
): SetupState {
  const current = state.overrides[subtopicId];
  const added = new Set(current?.added ?? []);
  const removed = new Set(current?.removed ?? []);
  change(added, removed);
  return { ...state, overrides: { ...state.overrides, [subtopicId]: { added, removed } } };
}

export function turnOff(
  state: SetupState,
  scope: Scope,
  styleIds: readonly string[],
  hiddenCounts: Readonly<Record<string, number>> | null,
): SetupState {
  let next: SetupState =
    scope === COURSE
      ? { ...state, courseOn: new Set([...state.courseOn].filter((id) => !styleIds.includes(id))) }
      : withOverride(state, scope, (added, removed) => {
          for (const id of styleIds) {
            added.delete(id);
            removed.add(id);
          }
        });
  if (hiddenCounts) {
    const hidden = { ...next.hidden };
    for (const [id, count] of Object.entries(hiddenCounts)) {
      if (count > 0) hidden[`${scope}|${id}`] = (hidden[`${scope}|${id}`] ?? 0) + count;
    }
    next = { ...next, hidden };
  }
  return next;
}

export function turnOn(
  state: SetupState,
  course: Course,
  scope: Scope,
  styleIds: readonly string[],
  showAgain: boolean,
): SetupState {
  let next: SetupState;
  if (scope === COURSE) {
    next = { ...state, courseOn: new Set([...state.courseOn, ...styleIds]) };
  } else {
    const ref = subtopics(course).find((entry) => entry.subtopic.id === scope);
    const fit = ref ? aiFit(course, ref) : new Set<string>();
    next = withOverride(state, scope, (added, removed) => {
      for (const id of styleIds) {
        removed.delete(id);
        if (!fit.has(id)) added.add(id);
      }
    });
  }
  if (showAgain) {
    const hidden = { ...next.hidden };
    for (const id of styleIds) delete hidden[`${scope}|${id}`];
    next = { ...next, hidden };
  }
  return next;
}

export function resetSubtopic(state: SetupState, subtopicId: string): SetupState {
  const { [subtopicId]: _dropped, ...rest } = state.overrides;
  return { ...state, overrides: rest };
}

export function hiddenCount(state: SetupState, scope: Scope, styleIds: readonly string[]): number {
  return styleIds.reduce((sum, id) => sum + (state.hidden[`${scope}|${id}`] ?? 0), 0);
}
