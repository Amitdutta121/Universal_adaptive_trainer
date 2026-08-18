"use client";

import { useEffect, useMemo, useState } from "react";
import type { QuestionDetail, RejectionReason, ReviewDecision } from "./review-types";

export function useReviewForm(detail: QuestionDetail | null) {
  const [decision, setDecision] = useState<ReviewDecision>("approve");
  const [reasons, setReasons] = useState<RejectionReason[]>([]);
  const [comment, setComment] = useState("");
  const [promptEdit, setPromptEdit] = useState("");
  const [referenceEdit, setReferenceEdit] = useState("");
  const [testsEdit, setTestsEdit] = useState("");

  useEffect(() => {
    if (!detail) return;
    setDecision("approve");
    setReasons([]);
    setComment("");
    setPromptEdit(detail.question.prompt);
    setReferenceEdit(detail.reference_solution ?? "");
    setTestsEdit(detail.tests ?? "");
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
    changedFields,
    effectiveDecision,
    isInlineEditing: decision === "edit" || effectiveDecision === "edit",
  };
}
