"use client";

import { ArrowRight, ArrowUpRight, CheckCircle2, XCircle } from "lucide-react";
import { useState } from "react";
import { PromptText } from "@/components/prompt-text";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { questionTypeLabel, questionTypeUI } from "@/lib/question-types/registry";
import { CodeAnswerInput } from "@/lib/question-types/text-answer";
import { cn } from "@/lib/utils";
import { AI_GAMES_QUESTIONS } from "./mock-ai-games";
import {
  FIGURE_KIND_LABEL,
  type MockFigureQuestion,
  OTHER_SUBJECT_QUESTIONS,
  type Variant,
} from "./mock-figure-questions";
import { QuestionFigure } from "./question-figure";

const COURSES: { name: string; questions: MockFigureQuestion[] }[] = [
  { name: "CS 681 AI in Games", questions: AI_GAMES_QUESTIONS },
  { name: "Other subjects", questions: OTHER_SUBJECT_QUESTIONS },
];

/** Mock check: the real app scores on the server. TODO(real): POST /answer. */
function isCorrect(variant: Variant, answer: string): boolean {
  if (variant.question.question_type === "numeric_response") {
    return Number.parseFloat(answer) === Number(variant.key);
  }
  return answer.trim() === variant.key;
}

function chipLabel(q: MockFigureQuestion): string {
  const first = q.variants[0];
  const kind = first.figure ? FIGURE_KIND_LABEL[first.figure.kind] : "Text only";
  return `${kind} · ${questionTypeLabel(first.question.question_type ?? "coding")}`;
}

export function FigureQuestionsExperience() {
  const [courseIndex, setCourseIndex] = useState(0);
  const [questionIndex, setQuestionIndex] = useState(0);
  const [variantIndex, setVariantIndex] = useState(0);
  const [answer, setAnswer] = useState("");
  const [submitted, setSubmitted] = useState(false);

  const questions = COURSES[courseIndex].questions;
  const item = questions[questionIndex];
  const variant = item.variants[variantIndex];
  const question = variant.question;
  const AnswerInput = questionTypeUI(question.question_type)?.AnswerInput ?? CodeAnswerInput;

  const reset = () => {
    setAnswer("");
    setSubmitted(false);
  };
  const pickQuestion = (index: number) => {
    setQuestionIndex(index);
    setVariantIndex(0);
    reset();
  };
  const pickVariant = (index: number) => {
    setVariantIndex(index);
    reset();
  };
  const correct = submitted && isCorrect(variant, answer);

  return (
    <main className="min-h-screen bg-background">
      <div className="mx-auto max-w-6xl space-y-6 px-5 py-8">
        <header className="space-y-1">
          <h1 className="font-semibold text-2xl text-foreground">Questions with figures</h1>
          <p className="text-muted-foreground text-sm">Student view. Mock data, real answer widgets.</p>
        </header>

        <div className="flex gap-1 border-border border-b" role="tablist" aria-label="Course">
          {COURSES.map((course, index) => (
            <button
              key={course.name}
              type="button"
              role="tab"
              aria-selected={index === courseIndex}
              onClick={() => {
                setCourseIndex(index);
                pickQuestion(0);
              }}
              className={cn(
                "-mb-px border-b-2 px-3 py-2 font-medium text-sm transition-colors",
                index === courseIndex
                  ? "border-primary text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground",
              )}
            >
              {course.name}
            </button>
          ))}
        </div>

        <nav className="flex flex-wrap gap-1.5" aria-label="Questions">
          {questions.map((q, index) => (
            <button
              key={q.id}
              type="button"
              onClick={() => pickQuestion(index)}
              className={cn(
                "rounded-full border px-3 py-1 text-sm transition-colors",
                index === questionIndex
                  ? "border-primary bg-primary text-primary-foreground"
                  : "border-border bg-card text-foreground hover:bg-muted",
              )}
            >
              {chipLabel(q)}
            </button>
          ))}
        </nav>

        {item.variants.length > 1 ? (
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="text-muted-foreground">Served to</span>
            {item.variants.map((v, index) => (
              <button
                key={v.seed}
                type="button"
                onClick={() => pickVariant(index)}
                className={cn(
                  "rounded-md border px-2.5 py-1 transition-colors",
                  index === variantIndex
                    ? "border-foreground/40 bg-muted font-medium text-foreground"
                    : "border-border bg-card text-muted-foreground hover:bg-muted",
                )}
              >
                Student {index + 1}
                <span className="ml-1.5 font-mono text-muted-foreground text-xs">
                  seed {v.seed}
                </span>
              </button>
            ))}
          </div>
        ) : null}

        <Card className="overflow-hidden rounded-[2rem] border border-white/70 bg-[linear-gradient(180deg,rgba(255,255,255,0.98),rgba(247,250,249,0.92))] shadow-[0_30px_80px_-48px_rgb(19_26_28_/_0.45)]">
          <CardHeader className="gap-4 border-border/60 border-b px-6 py-6 sm:px-7">
            <div className="flex flex-wrap items-center gap-2.5">
              <CardTitle className="text-[1.9rem] leading-none tracking-[-0.03em]">
                Question {questionIndex + 1}
              </CardTitle>
              <Badge variant="outline" className="rounded-full bg-background/80 px-3 py-1">
                {question.served_difficulty}
              </Badge>
              {question.question_type ? (
                <Badge variant="outline" className="rounded-full bg-background/80 px-3 py-1">
                  {questionTypeLabel(question.question_type)}
                </Badge>
              ) : null}
            </div>
            <div className="font-medium text-muted-foreground text-sm">
              {item.subject} · {question.subtopic_name}
            </div>
          </CardHeader>
          <CardContent className="space-y-5 px-6 py-6 sm:px-7 xl:grid xl:grid-cols-[minmax(0,7fr)_minmax(0,5fr)] xl:items-start xl:gap-8 xl:space-y-0">
            <div className="min-w-0 rounded-[1.5rem] border border-border/70 bg-white/80 p-5 shadow-[0_18px_40px_-34px_rgb(19_26_28_/_0.32)]">
              <div className="mb-3 flex items-center justify-between gap-3">
                <div className="font-medium text-[11px] text-muted-foreground uppercase tracking-[0.18em]">
                  Prompt
                </div>
                <ArrowUpRight className="size-4 text-muted-foreground" />
              </div>
              <div className="space-y-4">
                <PromptText
                  text={question.prompt}
                  className="wrap-anywhere text-[0.98rem] leading-8"
                />
                {variant.figure ? (
                  <QuestionFigure key={`${item.id}-${variantIndex}`} figure={variant.figure} />
                ) : null}
                {question.code ? (
                  <pre className="overflow-x-auto rounded-xl bg-slate-950 p-4 font-mono text-slate-50 text-sm leading-7">
                    {question.code}
                  </pre>
                ) : null}
              </div>
            </div>

            <div className="min-w-0 space-y-5">
              <AnswerInput
                key={question.attempt_id}
                question={question}
                value={answer}
                onChange={(value) => {
                  setAnswer(value);
                  setSubmitted(false);
                }}
                onSubmit={() => setSubmitted(true)}
              />
              <Button
                type="button"
                size="lg"
                disabled={answer.trim().length === 0}
                onClick={() => setSubmitted(true)}
                className="min-w-44 rounded-full px-5"
              >
                <ArrowRight />
                Submit answer
              </Button>
              {submitted ? (
                <div
                  className={cn(
                    "flex gap-3 rounded-xl border p-4 text-sm",
                    correct ? "border-emerald-500/30 bg-emerald-50" : "border-rose-500/30 bg-rose-50",
                  )}
                >
                  {correct ? (
                    <CheckCircle2 className="size-4 shrink-0 text-emerald-700" />
                  ) : (
                    <XCircle className="size-4 shrink-0 text-rose-700" />
                  )}
                  <div className="space-y-1">
                    <div className="font-medium">{correct ? "Correct" : "Not quite"}</div>
                    <p className="text-muted-foreground">{variant.explanation}</p>
                  </div>
                </div>
              ) : null}
            </div>
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
