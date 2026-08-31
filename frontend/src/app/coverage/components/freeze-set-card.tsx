"use client";

/** Freeze the approved bank as a named, immutable set (ADR-036). */

import { Snowflake } from "lucide-react";
import Link from "next/link";
import { useId, useState } from "react";
import { toast } from "sonner";
import { QueryError } from "@/components/query-state";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useCreateQuestionSet } from "@/lib/api/queries";
import type { CoverageReport, QuestionSetOut } from "@/lib/api/types";
import { pluralise } from "@/lib/display";
import { labelClashes } from "../coverage-display";

function DisabledCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Snowflake className="size-4 text-muted-foreground" />
          Freeze question set
        </CardTitle>
      </CardHeader>
      <CardContent>
        <Alert>
          <AlertTitle>{title}</AlertTitle>
          <AlertDescription>{children}</AlertDescription>
        </Alert>
      </CardContent>
    </Card>
  );
}

export function FreezeSetCard({
  liveReport,
  existingSets,
}: {
  liveReport: CoverageReport;
  existingSets: readonly QuestionSetOut[];
}) {
  const labelFieldId = useId();
  const notesFieldId = useId();
  const [label, setLabel] = useState("");
  const [notes, setNotes] = useState("");
  const createSet = useCreateQuestionSet();

  if (liveReport.curriculum_version_id === null) {
    return (
      <DisabledCard title="No curriculum is approved">
        Approve one on the{" "}
        <Link href="/curriculum" className="underline">
          Curriculum
        </Link>{" "}
        page first.
      </DisabledCard>
    );
  }

  if (liveReport.question_count === 0) {
    return (
      <DisabledCard title="Nothing is approved to freeze">
        Approve questions on the{" "}
        <Link href="/review" className="underline">
          Review
        </Link>{" "}
        page first.
      </DisabledCard>
    );
  }

  const clashes = labelClashes(label, existingSets);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const clean = label.trim();
    if (!clean) return;
    createSet.reset();
    try {
      const created = await createSet.mutateAsync({
        label: clean,
        notes: notes.trim() || null,
      });
      toast.success(`Froze “${created.label}”`, {
        description: `${pluralise(created.question_count, "question")}, snapshot #${created.id}.`,
      });
      setLabel("");
      setNotes("");
    } catch {
      // Shown from createSet.error below.
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Snowflake className="size-4 text-muted-foreground" />
          Freeze question set
        </CardTitle>
        <CardDescription>
          Snapshots all {pluralise(liveReport.question_count, "approved question")} of{" "}
          {liveReport.curriculum_label}.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor={labelFieldId}>Label</Label>
            <Input
              id={labelFieldId}
              value={label}
              onChange={(event) => setLabel(event.target.value)}
              maxLength={200}
              className="max-w-md"
            />
            {clashes ? (
              <p className="text-amber-700 text-xs dark:text-amber-400">
                Another set already uses this label.
              </p>
            ) : null}
          </div>

          <div className="space-y-2">
            <Label htmlFor={notesFieldId}>Notes (optional)</Label>
            <Textarea
              id={notesFieldId}
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              className="h-[6rem]"
            />
          </div>

          <Button type="submit" disabled={!label.trim() || createSet.isPending}>
            {createSet.isPending ? "Freezing…" : "Freeze this bank"}
          </Button>

          {createSet.error ? <QueryError error={createSet.error} /> : null}
        </form>
      </CardContent>
    </Card>
  );
}
