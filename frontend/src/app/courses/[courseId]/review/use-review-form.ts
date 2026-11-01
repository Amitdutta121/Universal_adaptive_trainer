"use client";

import { useEffect, useMemo, useState } from "react";
import type {
  Difficulty,
  QuestionDetail,
  RejectionReason,
  ReviewDecision,
} from "./review-types";

function judgeMetric(detail: QuestionDetail, metric: "difficulty" | "subtopic") {
  return detail.pedagogical_eval?.metrics?.find((item) => item.metric === metric) ?? null;
}

/** The difficulty the form opens on: the judge's proposal, else the question's own. */
export function presetDifficulty(detail: QuestionDetail): Difficulty {
  return judgeMetric(detail, "difficulty")?.proposed_difficulty ?? detail.question.difficulty;
}

/** The subtopics the form opens on: the judge's proposal, else the question's own. */
export function presetSubtopicIds(detail: QuestionDetail): number[] {
  const proposed = judgeMetric(detail, "subtopic")?.proposed_subtopic_ids ?? [];
  return proposed.length > 0 ? [...proposed] : [...detail.question.subtopic_ids];
}

export function useReviewForm(detail: QuestionDetail | null) {
  const [decision, setDecision] = useState<ReviewDecision>("approve");
  const [comment, setComment] = useState("");
  // Optional structured reasons for a reject or an edit; they say which judge was wrong.
  const [reasons, setReasons] = useState<RejectionReason[]>([]);
  const [promptEdit, setPromptEdit] = useState("");
  const [referenceEdit, setReferenceEdit] = useState("");
  const [testsEdit, setTestsEdit] = useState("");
  // The professor's final difficulty and subtopics. Always sent with the review; the
  // backend compares them to the judges' answers to decide who was right.
  const [difficulty, setDifficulty] = useState<Difficulty>("medium");
  const [subtopicIds, setSubtopicIds] = useState<number[]>([]);
  const [difficultyConfirmed, setDifficultyConfirmed] = useState(false);
  const [subtopicsConfirmed, setSubtopicsConfirmed] = useState(false);

  useEffect(() => {
    if (!detail) return;
    setDecision(detail.question.audit ? "reject" : "approve");
    setComment("");
    setReasons([]);
    setPromptEdit(detail.question.prompt);
    setReferenceEdit(detail.reference_solution ?? "");
    setTestsEdit(detail.tests ?? "");
    setDifficulty(presetDifficulty(detail));
    setSubtopicIds(presetSubtopicIds(detail));
    setDifficultyConfirmed(false);
    setSubtopicsConfirmed(false);
  }, [detail]);

  const changedFields = useMemo(() => {
    if (!detail) return [] as string[];
    const fields: string[] = [];
    if (promptEdit !== detail.question.prompt) fields.push("prompt");
    if (referenceEdit !== (detail.reference_solution ?? "")) fields.push("reference_solution");
    if (testsEdit !== (detail.tests ?? "")) fields.push("tests");
    return fields;
  }, [detail, promptEdit, referenceEdit, testsEdit]);

  const effectiveDecision: ReviewDecision =
    decision === "approve" && changedFields.length > 0 ? "edit" : decision;

  return {
    decision,
    setDecision,
    comment,
    setComment,
    reasons,
    setReasons,
    promptEdit,
    setPromptEdit,
    referenceEdit,
    setReferenceEdit,
    testsEdit,
    setTestsEdit,
    difficulty,
    setDifficulty: (value: Difficulty) => {
      setDifficulty(value);
      setDifficultyConfirmed(true);
    },
    subtopicIds,
    setSubtopicIds: (value: number[]) => {
      setSubtopicIds(value);
      setSubtopicsConfirmed(true);
    },
    difficultyConfirmed,
    subtopicsConfirmed,
    confirmDifficulty: () => setDifficultyConfirmed(true),
    confirmSubtopics: () => setSubtopicsConfirmed(true),
    changedFields,
    effectiveDecision,
    isInlineEditing: decision === "edit" || effectiveDecision === "edit",
  };
}
