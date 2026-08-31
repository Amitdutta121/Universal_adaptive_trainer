"use client";

/** Type + difficulty for the one question about to be generated from a chunk. */

import type * as React from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { Difficulty, QuestionKind, QuestionType } from "@/lib/api/types";
import { DIFFICULTIES, QUESTION_TYPE_LABEL, QUESTION_TYPES } from "../../spec-sheet-types";

/** Not exposed as a client constant elsewhere — mirrors `app.domain.enums`'s split. */
const QUESTION_TYPE_KIND: Record<QuestionType, QuestionKind> = {
  multiple_choice: "discrete",
  true_false: "discrete",
  output_prediction: "testable_program",
  code_completion: "testable_program",
  debugging: "testable_program",
  parsons: "testable_program",
  coding: "testable_program",
};

function Pill({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={
        active
          ? "rounded-full bg-primary px-3 py-1.5 font-medium text-primary-foreground text-sm"
          : "rounded-full border px-3 py-1.5 text-sm hover:bg-muted"
      }
    >
      {children}
    </button>
  );
}

export function GenerateControls({
  type,
  onTypeChange,
  difficulty,
  onDifficultyChange,
  onGenerate,
  isGenerating,
}: {
  type: QuestionType;
  onTypeChange: (value: QuestionType) => void;
  difficulty: Difficulty;
  onDifficultyChange: (value: Difficulty) => void;
  onGenerate: () => void;
  isGenerating: boolean;
}) {
  return (
    <Card className="border">
      <CardHeader>
        <CardTitle>Generate</CardTitle>
        <CardDescription>One question, from the chunk selected on the left.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-1.5">
          <span className="font-mono text-[0.67rem] text-muted-foreground uppercase tracking-[0.16em]">
            Question type
          </span>
          <div className="flex flex-wrap gap-1.5">
            {QUESTION_TYPES.map((value) => (
              <Pill key={value} active={value === type} onClick={() => onTypeChange(value)}>
                {QUESTION_TYPE_LABEL[value]}
              </Pill>
            ))}
          </div>
          <p className="text-[0.7rem] text-muted-foreground">
            Question kind{" "}
            <span className="rounded bg-muted px-1 py-0.5 font-mono">
              {QUESTION_TYPE_KIND[type]}
            </span>{" "}
            — set automatically from the type, matching how the grader executes it.
          </p>
        </div>

        <div className="space-y-1.5">
          <span className="font-mono text-[0.67rem] text-muted-foreground uppercase tracking-[0.16em]">
            Difficulty
          </span>
          <div className="flex flex-wrap gap-1.5">
            {DIFFICULTIES.map((value) => (
              <Pill
                key={value}
                active={value === difficulty}
                onClick={() => onDifficultyChange(value)}
              >
                {value[0].toUpperCase()}
                {value.slice(1)}
              </Pill>
            ))}
          </div>
        </div>

        <button
          type="button"
          onClick={onGenerate}
          disabled={isGenerating}
          className="w-full rounded-md bg-primary py-2 font-medium text-primary-foreground text-sm disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isGenerating ? "Generating…" : "Generate one question"}
        </button>
      </CardContent>
    </Card>
  );
}
