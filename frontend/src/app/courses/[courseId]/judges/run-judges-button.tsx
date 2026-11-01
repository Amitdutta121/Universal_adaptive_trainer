"use client";

/**
 * "Run judges": re-judge every eligible question of the course in one provider batch.
 *
 * The batch costs credits and takes up to a day, so the button first says how many
 * questions it will send, and is off (with the reason) when re-runs are switched off
 * or one is already running. Results are collected on the server and the run shows
 * in Jobs, so nothing here waits for them.
 */

import { Gavel } from "lucide-react";
import { parseAsString, useQueryState } from "nuqs";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { ApiError } from "@/lib/api/client";
import { useJudgeRerunPreview, useRunJudges } from "@/lib/api/queries";
import { pluralise } from "@/lib/display";

export function RunJudgesButton() {
  const preview = useJudgeRerunPreview();
  const runJudges = useRunJudges();
  const [confirming, setConfirming] = useState(false);
  const [, setJobParam] = useQueryState("job", parseAsString);

  const data = preview.data;
  const eligible = data?.eligible ?? 0;
  const blockedBy = !data
    ? null
    : data.disabled_reason
      ? data.disabled_reason
      : data.active_run_id
        ? "A judge run is already in progress. Its results arrive in Jobs."
        : eligible === 0
          ? "No question has passed validation yet, so there is nothing to judge."
          : null;

  async function submit() {
    try {
      const started = await runJudges.mutateAsync();
      setConfirming(false);
      toast.success(`Judge run started for ${pluralise(started.submitted, "question")}`, {
        description: "Results are collected automatically and can take a while.",
        action: {
          label: "View",
          onClick: () => void setJobParam(`judge-${started.run.run_id}`),
        },
      });
    } catch (error) {
      toast.error("Could not start the judge run", {
        description: error instanceof ApiError ? (error.detail ?? error.message) : undefined,
      });
    }
  }

  const unavailable = preview.isPending || blockedBy !== null;
  // `aria-disabled` rather than `disabled`: a disabled button takes no focus or hover,
  // so the tooltip saying *why* it is off could never be read.
  const button = (
    <Button
      variant="outline"
      size="sm"
      className="h-9 aria-disabled:cursor-not-allowed aria-disabled:opacity-50"
      aria-disabled={unavailable}
      onClick={() => (unavailable ? null : setConfirming(true))}
    >
      <Gavel className="size-4" /> Run judges
    </Button>
  );

  return (
    <>
      {blockedBy ? (
        <Tooltip>
          <TooltipTrigger asChild>{button}</TooltipTrigger>
          <TooltipContent className="max-w-72">{blockedBy}</TooltipContent>
        </Tooltip>
      ) : (
        button
      )}

      <Dialog open={confirming} onOpenChange={setConfirming}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Re-judge {pluralise(eligible, "question")}?</DialogTitle>
            <DialogDescription>
              Every question of this course that passed validation is sent to the judges again as
              one batch. It uses model credits and can take up to a day. Earlier evaluations are
              kept; results are collected automatically and show in Jobs.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <DialogClose asChild>
              <Button variant="outline">Cancel</Button>
            </DialogClose>
            <Button onClick={() => void submit()} disabled={runJudges.isPending}>
              {runJudges.isPending ? "Starting…" : `Run judges on ${eligible}`}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
