"use client";

/**
 * One predict-then-reveal experiment: the snippet, a prediction (tap an option, or type a number),
 * then the real output and one sentence of insight. Focus moves to the step heading when the step
 * appears (after the first one) and to "Next" once the answer is revealed; the reveal itself sits in
 * a polite live region so it is announced.
 */

import { ArrowRight, CircleCheck, Lightbulb } from "lucide-react";
import { type FormEvent, useEffect, useId, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  type Answer,
  type Experiment,
  experimentOutput,
  judgeGuess,
  optionLabel,
  parseTotalGuess,
} from "../mock-data";
import { CodeBox, Inline, OutputBox } from "./parts";

export function ExperimentStep({
  experiment,
  answer,
  onAnswer,
  onNext,
  nextLabel,
  focusHeading,
}: {
  experiment: Experiment;
  answer: Answer | undefined;
  onAnswer: (answer: Answer) => void;
  onNext: () => void;
  nextLabel: string;
  focusHeading: boolean;
}) {
  const headingRef = useRef<HTMLHeadingElement>(null);
  const nextRef = useRef<HTMLButtonElement>(null);
  const revealed = answer !== undefined;

  useEffect(() => {
    if (focusHeading) headingRef.current?.focus();
  }, [focusHeading]);

  useEffect(() => {
    if (revealed) nextRef.current?.focus();
  }, [revealed]);

  return (
    <div className="grid gap-4">
      <h2
        ref={headingRef}
        tabIndex={-1}
        className="rounded font-heading font-semibold text-xl outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
      >
        {experiment.question}
      </h2>

      <CodeBox code={experiment.code} label="Python snippet" />

      {revealed ? null : <Prediction experiment={experiment} onAnswer={onAnswer} />}

      <div role="status" aria-label="Result" className="grid gap-4">
        {answer ? <Reveal experiment={experiment} answer={answer} /> : null}
      </div>

      {answer ? (
        <div>
          <Button ref={nextRef} type="button" onClick={onNext}>
            {nextLabel}
            <ArrowRight aria-hidden="true" />
          </Button>
        </div>
      ) : null}
    </div>
  );
}

function Prediction({
  experiment,
  onAnswer,
}: {
  experiment: Experiment;
  onAnswer: (answer: Answer) => void;
}) {
  if (experiment.kind === "print" && experiment.options) {
    return (
      <fieldset className="m-0 grid min-w-0 gap-2 border-0 p-0">
        <legend className="sr-only">Your prediction</legend>
        {experiment.options.map((option) => (
          <Button
            key={optionLabel(option)}
            type="button"
            variant="outline"
            className="h-10 justify-start font-mono"
            onClick={() => onAnswer(judgeGuess(experiment, optionLabel(option)))}
          >
            {optionLabel(option)}
          </Button>
        ))}
      </fieldset>
    );
  }
  return <TotalPrediction experiment={experiment} onAnswer={onAnswer} />;
}

function TotalPrediction({
  experiment,
  onAnswer,
}: {
  experiment: Experiment;
  onAnswer: (answer: Answer) => void;
}) {
  const inputId = useId();
  const errorId = useId();
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);

  function submit(event: FormEvent) {
    event.preventDefault();
    const parsed = parseTotalGuess(text);
    if (!parsed.ok) {
      setError(parsed.message);
      return;
    }
    onAnswer(judgeGuess(experiment, parsed.value));
  }

  return (
    <form onSubmit={submit} noValidate className="grid gap-2">
      <Label htmlFor={inputId}>Your total</Label>
      <div className="flex gap-2">
        <Input
          id={inputId}
          type="text"
          inputMode="numeric"
          autoComplete="off"
          value={text}
          maxLength={16}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? errorId : undefined}
          className="h-10 max-w-40 font-mono"
          onChange={(event) => {
            setText(event.target.value);
            setError(null);
          }}
        />
        <Button type="submit" className="h-10">
          Reveal
        </Button>
      </div>
      {error ? (
        <p id={errorId} role="alert" className="text-amber-700 text-sm dark:text-amber-300">
          {error}
        </p>
      ) : null}
    </form>
  );
}

function Reveal({ experiment, answer }: { experiment: Experiment; answer: Answer }) {
  const Icon = answer.correct ? CircleCheck : Lightbulb;
  return (
    <>
      <p
        className={
          answer.correct
            ? "flex items-center gap-2 font-medium text-primary"
            : "flex items-center gap-2 font-medium text-amber-700 dark:text-amber-300"
        }
      >
        <Icon className="size-4 shrink-0" aria-hidden="true" />
        {answer.correct ? "You called it." : "Surprise. Worth remembering."}
      </p>
      <OutputBox label="Output">{experimentOutput(experiment).join("\n")}</OutputBox>
      {answer.correct ? null : (
        <p className="text-muted-foreground text-sm">
          You said <code className="font-mono text-foreground">{answer.guess}</code>
        </p>
      )}
      <p className="text-base">
        <Inline text={experiment.insight} />
      </p>
    </>
  );
}
