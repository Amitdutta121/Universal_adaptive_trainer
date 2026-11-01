/**
 * Pure logic behind the prototype: which templates make the deck, what a skip teaches the
 * generator, and the blueprint plan built from approved templates.
 *
 * The plan rule mirrors the real system: the adaptive engine picks a subtopic, then a
 * difficulty (ADR-041), and coverage wants `MIN_QUESTIONS_PER_CELL` approved questions in each
 * subtopic x difficulty cell (`app/coverage/schema.py`). Gaps are filled round-robin from the
 * approved templates of that difficulty that can be used for the topic.
 */

import {
  DIFFICULTIES,
  type Difficulty,
  type Domain,
  type SkipReason,
  type Subtopic,
  type Template,
  type Topic,
} from "./mock-types";

/** Same floor as `MIN_QUESTIONS_PER_CELL` in `app/coverage/schema.py`. */
export const FLOOR_PER_CELL = 3;

// TODO(real): read the course's own first-review approval rate; 0.59 is what the dev database
// shows for the Python course (94 approved of 160 reviewed).
export const EXPECTED_APPROVAL = 0.6;
// TODO(real): price from the configured model and the measured tokens per draft.
export const COST_PER_DRAFT_USD = 0.02;
// TODO(real): from the batch generator's measured throughput.
export const DRAFTS_PER_MINUTE = 6;

export interface Decision {
  verdict: "approved" | "skipped";
  reason: SkipReason | null;
}

/** The templates shown in the deck, after the professor's wishes are applied. */
export function deckFor(domain: Domain, wishes: ReadonlySet<string>): Template[] {
  const fewerTrueFalse = [...wishes].some((wish) => wish.toLowerCase().includes("fewer true"));
  return domain.templates.filter(
    (template) => !(fewerTrueFalse && template.questionType === "true_false"),
  );
}

export function approvedIds(decisions: Readonly<Record<string, Decision>>): Set<string> {
  return new Set(
    Object.entries(decisions)
      .filter(([, decision]) => decision.verdict === "approved")
      .map(([id]) => id),
  );
}

export function approvedByDifficulty(
  templates: readonly Template[],
  decisions: Readonly<Record<string, Decision>>,
): Record<Difficulty, number> {
  const counts: Record<Difficulty, number> = { easy: 0, medium: 0, hard: 0 };
  for (const template of templates) {
    if (decisions[template.id]?.verdict === "approved") counts[template.difficulty] += 1;
  }
  return counts;
}

/**
 * What the generator would be told after the professor's skips. A skip with a reason becomes a
 * rule; a skip with no reason only drops the style.
 * TODO(real): the learned-rules call (`app/personalization/instructions.py`) writes these.
 */
export function rulesFromSkips(
  templates: readonly Template[],
  decisions: Readonly<Record<string, Decision>>,
  typeLabels: Readonly<Record<string, string>>,
): string[] {
  const rules: string[] = [];
  for (const template of templates) {
    const decision = decisions[template.id];
    if (decision?.verdict !== "skipped" || decision.reason === null) continue;
    const type = typeLabels[template.questionType] ?? template.questionType;
    const name = template.name.toLowerCase();
    switch (decision.reason) {
      case "Not this kind of question":
        rules.push(`Don't write ${type} questions that ${name}.`);
        break;
      case "Too easy":
        rules.push(`${type} questions at ${template.difficulty} level should need more than one step.`);
        break;
      case "Too hard":
        rules.push(`Keep ${template.difficulty} ${type} questions within what one section teaches.`);
        break;
      case "Wrong or unclear":
        rules.push(`For ${type} questions, state every assumption and double-check the answer key.`);
        break;
      case "Not in my course":
        rules.push(`Only assess what the approved taxonomy covers; avoid content like "${template.examples[0].grounding}".`);
        break;
    }
  }
  return rules;
}

export interface PlanCell {
  have: number;
  add: number;
  /** Why a gap cannot be filled: nothing approved at this level, or nothing usable for the topic. */
  blocked: "no-style" | "not-applicable" | null;
  mix: { templateId: string; count: number }[];
}

export interface PlanSubtopic {
  subtopic: Subtopic;
  excluded: boolean;
  cells: Record<Difficulty, PlanCell>;
}

export interface PlanTopic {
  topic: Topic;
  subtopics: PlanSubtopic[];
}

export interface Plan {
  topics: PlanTopic[];
  totalAdd: number;
  drafts: number;
  costUsd: number;
  minutes: number;
  blockedCells: number;
  cellsTotal: number;
  cellsReady: number;
  byTemplate: Map<string, number>;
}

function fillCell(
  have: number,
  usable: readonly Template[],
  anyApproved: boolean,
  offset: number,
): PlanCell {
  const gap = Math.max(0, FLOOR_PER_CELL - have);
  if (gap === 0) return { have, add: 0, blocked: null, mix: [] };
  if (usable.length === 0) {
    return { have, add: 0, blocked: anyApproved ? "not-applicable" : "no-style", mix: [] };
  }
  const counts = new Map<string, number>();
  for (let index = 0; index < gap; index += 1) {
    const template = usable[(offset + index) % usable.length];
    if (template) counts.set(template.id, (counts.get(template.id) ?? 0) + 1);
  }
  return {
    have,
    add: gap,
    blocked: null,
    mix: [...counts].map(([templateId, count]) => ({ templateId, count })),
  };
}

export function buildPlan(
  domain: Domain,
  templates: readonly Template[],
  approved: ReadonlySet<string>,
  excluded: ReadonlySet<string>,
): Plan {
  const byTemplate = new Map<string, number>();
  let totalAdd = 0;
  let blockedCells = 0;
  let cellsTotal = 0;
  let cellsReady = 0;
  let offset = 0;

  const topics = domain.topics.map((topic) => ({
    topic,
    subtopics: topic.subtopics.map((subtopic) => {
      const isExcluded = excluded.has(subtopic.id);
      const cells = {} as Record<Difficulty, PlanCell>;
      for (const difficulty of DIFFICULTIES) {
        const atLevel = templates.filter(
          (template) => template.difficulty === difficulty && approved.has(template.id),
        );
        const usable = atLevel.filter((template) => !template.excludeTopics?.includes(topic.id));
        const have = subtopic.have[difficulty];
        const cell = isExcluded
          ? { have, add: 0, blocked: null, mix: [] }
          : fillCell(have, usable, atLevel.length > 0, offset);
        cells[difficulty] = cell;
        offset += 1;
        if (isExcluded) continue;
        cellsTotal += 1;
        if (cell.blocked) blockedCells += 1;
        else cellsReady += 1;
        totalAdd += cell.add;
        for (const { templateId, count } of cell.mix) {
          byTemplate.set(templateId, (byTemplate.get(templateId) ?? 0) + count);
        }
      }
      return { subtopic, excluded: isExcluded, cells };
    }),
  }));

  const drafts = Math.ceil(totalAdd / EXPECTED_APPROVAL);
  return {
    topics,
    totalAdd,
    drafts,
    costUsd: drafts * COST_PER_DRAFT_USD,
    minutes: Math.max(1, Math.ceil(drafts / DRAFTS_PER_MINUTE)),
    blockedCells,
    cellsTotal,
    cellsReady,
    byTemplate,
  };
}
