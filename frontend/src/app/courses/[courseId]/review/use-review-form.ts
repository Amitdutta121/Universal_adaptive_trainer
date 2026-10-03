"use client";

import { useEffect, useMemo, useState } from "react";
import type { Difficulty, QuestionDetail, RejectionReason, ReviewDecision } from "./review-types";

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
  const [reasons, setReasons] = useState<RejectionReason[]>([]);
  const [comment, setComment] = useState("");
  const [promptEdit, setPromptEdit] = useState("");
  const [referenceEdit, setReferenceEdit] = useState("");
  const [testsEdit, setTestsEdit] = useState("");
  // The professor's final difficulty and subtopics. Always sent with the review; the
  // backend compares them to the judges' answers to decide who was right.
  const [difficulty, setDifficulty] = useState<Difficulty>("medium");
  const [subtopicIds, setSubtopicIds] = useState<number[]>([]);

  useEffect(() => {
    if (!detail) return;
    setDecision("approve");
    setReasons([]);
    setComment("");
    setPromptEdit(detail.question.prompt);
    setReferenceEdit(detail.reference_solution ?? "");
    setTestsEdit(detail.tests ?? "");
    setDifficulty(presetDifficulty(detail));
    setSubtopicIds(presetSubtopicIds(detail));
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
    reasons,
    setReasons,
    comment,
    setComment,
    promptEdit,
    setPromptEdit,
    referenceEdit,
    setReferenceEdit,
    testsEdit,
    setTestsEdit,
    difficulty,
    setDifficulty,
    subtopicIds,
    setSubtopicIds,
    changedFields,
    effectiveDecision,
    isInlineEditing: decision === "edit" || effectiveDecision === "edit",
  };
}
