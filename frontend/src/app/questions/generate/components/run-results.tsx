"use client";

/**
 * What a finished run produced.
 *
 * A run is not atomic: each question commits on its own, so a batch can end with
 * fewer questions than it planned and that is a real outcome, not an error. This
 * says how many of the planned questions arrived and links every one of them, so
 * a short run reads as a short run rather than as a failure or a success.
 */

import { CheckCircle2 } from "lucide-react";
import Link from "next/link";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import type { Schemas } from "@/lib/api/types";

type GenerateBatchResponse = Schemas["GenerateBatchResponse"];

export function RunResults({ result }: { result: GenerateBatchResponse }) {
  const planned = result.planned.length;
  const short = result.created < planned;
  const failedValidation = result.questions.filter(
    (question) => question.validation_passed === false,
  ).length;

  return (
    <Alert className="border-primary/40">
      <CheckCircle2 />
      <AlertTitle>
        {result.created} of {planned} questions generated
      </AlertTitle>
      <AlertDescription className="space-y-2">
        {short ? (
          <p>
            The run stopped early. Everything listed below is saved and reviewable; the rest was
            never generated, so nothing was spent on it.
          </p>
        ) : null}
        {failedValidation > 0 ? (
          <p>
            {failedValidation} failed deterministic validation. They are kept and flagged, and will
            not enter the review queue.
          </p>
        ) : null}
        <ul className="flex flex-wrap gap-1.5">
          {result.questions.map((question) => (
            <li key={question.id}>
              <Link href={`/questions/${question.id}`}>
                <Badge
                  variant={question.validation_passed === false ? "destructive" : "secondary"}
                  className="font-mono text-[0.65rem]"
                >
                  #{question.id} {question.difficulty}
                </Badge>
              </Link>
            </li>
          ))}
        </ul>
      </AlertDescription>
    </Alert>
  );
}
