"use client";

import { useQueryClient } from "@tanstack/react-query";
import { parseAsInteger, useQueryState } from "nuqs";
import { useEffect, useRef } from "react";
import { toast } from "sonner";
import { readApiError } from "@/lib/api/client";
import { qk, useCurrentSetup, useRound, useStartNextRound } from "@/lib/api/queries";

/** Questions asked for per round (docs/QUESTION_SETUP_PLAN.md). */
export const ROUND_SIZE = 10;

/** A sentence a professor can act on, for any error the setup and round endpoints throw. */
export function describeRoundError(error: unknown): string {
  const api = readApiError(error);
  if (api?.isNotImplemented) return "Round generation is not available on this server yet.";
  if (api) return api.detail ? `${api.message} ${api.detail}` : api.message;
  return error instanceof Error ? error.message : "Something went wrong.";
}

/**
 * The "Generate next round" control of the review queue.
 *
 * The round being watched lives in the URL (`?round=`) so a reload keeps polling it. Without
 * one, a round of the current setup that is still queued or running is watched instead, so
 * landing here from the setup modal shows round 1's progress too. Each question a round
 * produces is committed and reviewable at once, so the queue is refetched as every one lands:
 * the professor reviews the first while the rest are generated. When the round finishes, the
 * queue and the setup are refetched.
 */
export function useNextRound(curriculumVersionId: number | null | undefined) {
  const client = useQueryClient();
  const [roundParam, setRoundParam] = useQueryState("round", parseAsInteger);
  const setupQuery = useCurrentSetup(curriculumVersionId);
  const setup = setupQuery.data?.setup ?? null;
  const latest = setup?.latest_round ?? null;
  const latestActive =
    latest && (latest.status === "queued" || latest.status === "running") ? latest.id : null;
  const roundId = roundParam ?? latestActive;

  const roundQuery = useRound(roundId);
  const round = roundQuery.data ?? null;
  const isActive = round ? round.status === "queued" || round.status === "running" : false;
  const start = useStartNextRound();

  // Pin a running round found through the setup into the URL, so its outcome stays on screen
  // after it finishes and a reload keeps watching it.
  useEffect(() => {
    if (roundParam == null && latestActive != null) void setRoundParam(latestActive);
  }, [roundParam, latestActive, setRoundParam]);

  const produced = round?.produced ?? 0;
  useEffect(() => {
    if (produced === 0) return;
    void client.invalidateQueries({ queryKey: ["questions", "review-queue"] });
  }, [client, produced]);

  const refreshedFor = useRef<number | null>(null);
  useEffect(() => {
    if (!round || refreshedFor.current === round.id) return;
    if (round.status !== "done" && round.status !== "failed") return;
    refreshedFor.current = round.id;
    void client.invalidateQueries({ queryKey: ["questions", "review-queue"] });
    void client.invalidateQueries({ queryKey: qk.setup.all });
  }, [client, round]);

  const disabledReason = !setup
    ? setupQuery.isError
      ? describeRoundError(setupQuery.error)
      : "Set up questions on the Questions page first."
    : isActive
      ? "A round is already generating."
      : null;

  async function startNext() {
    if (!setup || start.isPending || isActive) return;
    try {
      const result = await start.mutateAsync({ setup_id: setup.id, size: ROUND_SIZE });
      await setRoundParam(result.round_id);
    } catch (caught) {
      toast.error("Next round not started", { description: describeRoundError(caught) });
    }
  }

  return {
    setup,
    roundId,
    round,
    roundError: roundQuery.isError ? describeRoundError(roundQuery.error) : null,
    isGenerating: isActive,
    isStarting: start.isPending,
    canStart: disabledReason === null && !start.isPending,
    disabledReason,
    startNext,
    dismiss: () => void setRoundParam(null),
  };
}
