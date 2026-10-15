"use client";

/**
 * Pre-generate a taxonomy's tutorial blocks and approve them by recipe (Phase 6, Task 24).
 *
 * "Price it" is a `dry_run` of `POST /api/tutorial-pregeneration`: every subtopic x recipe x
 * guidance level the bank is still missing, one model call each. Starting it queues one job
 * that the Jobs panel follows. Below, each recipe shows a sample of its blocks and is approved
 * or rejected for the whole taxonomy: its blocks follow, rejected ones are hidden, and only
 * approved ones are frozen with a question set and shown to students.
 */

import { useState } from "react";
import { toast } from "sonner";
import { QueryError, TableSkeleton } from "@/components/query-state";
import { TutorialBlockView } from "@/components/tutorial/renderer-registry";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  useDecideTutorialRecipe,
  usePregenerateTutorials,
  useTutorialRecipes,
  useTutorialSample,
} from "@/lib/api/queries";
import type { Schemas } from "@/lib/api/types";

type Plan = Schemas["TutorialPregenerationPlan"];

function errorText(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}

export function RecipeApproval({ versionId }: { versionId: number }) {
  const recipes = useTutorialRecipes(versionId);
  const pregenerate = usePregenerateTutorials();
  const decide = useDecideTutorialRecipe();
  const [plan, setPlan] = useState<Plan | null>(null);
  const [sampled, setSampled] = useState<string | null>(null);

  if (recipes.isPending) return <TableSkeleton rows={3} />;
  if (recipes.isError) return <QueryError error={recipes.error} />;

  async function price() {
    try {
      const result = await pregenerate.mutateAsync({
        curriculum_version_id: versionId,
        dry_run: true,
      });
      setPlan(result as Plan);
    } catch (error) {
      toast.error("Could not price the blocks", { description: errorText(error, "") });
    }
  }

  async function start() {
    try {
      await pregenerate.mutateAsync({ curriculum_version_id: versionId, dry_run: false });
      setPlan(null);
      toast.success("Generating tutorial blocks", { description: "Follow it in Jobs." });
    } catch (error) {
      toast.error("Could not start", { description: errorText(error, "") });
    }
  }

  async function setDecision(recipeId: string, approved: boolean) {
    try {
      const result = await decide.mutateAsync({
        recipeId,
        curriculum_version_id: versionId,
        approved,
      });
      const count = result.blocks_changed;
      toast.success(approved ? "Recipe approved" : "Recipe rejected", {
        description: `${count} block${count === 1 ? "" : "s"} ${approved ? "approved" : "hidden"}.`,
      });
    } catch (error) {
      toast.error("Could not save the decision", { description: errorText(error, "") });
    }
  }

  const decisions = recipes.data.decisions ?? {};

  return (
    <Card>
      <CardHeader>
        <CardTitle>Pre-generate and approve by recipe</CardTitle>
        <CardDescription>
          Students only see blocks of approved recipes, frozen with the question set they train on.
          Look at a sample of each recipe's blocks, then approve or reject the recipe for the whole
          taxonomy.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-center gap-3">
          <Button variant="outline" onClick={price} disabled={pregenerate.isPending}>
            Price missing blocks
          </Button>
          {plan ? (
            plan.blocks_to_create === 0 ? (
              <span className="text-muted-foreground text-sm">
                Every block is made ({plan.already_made} in the bank).
              </span>
            ) : (
              <>
                <span className="text-sm">
                  {plan.blocks_to_create} blocks · {plan.generation_calls} model calls (up to{" "}
                  {plan.generation_calls * plan.max_attempts_per_block} with repairs) ·{" "}
                  {plan.already_made} already made
                </span>
                <Button onClick={start} disabled={pregenerate.isPending}>
                  Generate {plan.blocks_to_create} blocks
                </Button>
              </>
            )
          ) : null}
        </div>

        <ul className="divide-y rounded-md border">
          {recipes.data.recipes.map((recipe) => {
            const decision = decisions[recipe.id];
            return (
              <li key={recipe.id} className="space-y-3 p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{recipe.name}</span>
                  <Badge
                    variant={
                      decision === undefined ? "outline" : decision ? "secondary" : "destructive"
                    }
                  >
                    {decision === undefined ? "undecided" : decision ? "approved" : "rejected"}
                  </Badge>
                  <span className="text-muted-foreground text-sm">{recipe.summary}</span>
                  <div className="ml-auto flex gap-2">
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => setSampled(sampled === recipe.id ? null : recipe.id)}
                    >
                      {sampled === recipe.id ? "Hide sample" : "View sample"}
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={decide.isPending || decision === false}
                      onClick={() => setDecision(recipe.id, false)}
                    >
                      Reject
                    </Button>
                    <Button
                      size="sm"
                      disabled={decide.isPending || decision === true}
                      onClick={() => setDecision(recipe.id, true)}
                    >
                      Approve
                    </Button>
                  </div>
                </div>
                {sampled === recipe.id ? (
                  <RecipeSample versionId={versionId} recipeId={recipe.id} />
                ) : null}
              </li>
            );
          })}
        </ul>
      </CardContent>
    </Card>
  );
}

function RecipeSample({ versionId, recipeId }: { versionId: number; recipeId: string }) {
  const sample = useTutorialSample(versionId, recipeId);
  if (sample.isPending) return <TableSkeleton rows={1} />;
  if (sample.isError) return <QueryError error={sample.error} />;
  if (sample.data.length === 0) {
    return (
      <p className="text-muted-foreground text-sm">
        No blocks of this recipe yet. Price and generate the missing blocks above.
      </p>
    );
  }
  return (
    <div className="grid gap-3 md:grid-cols-3">
      {sample.data.map((block) => (
        <div key={block.id} className="space-y-2 rounded-md border p-3">
          <div className="flex gap-2">
            <Badge variant="outline">{block.guidance_level}</Badge>
            {block.status === "failed" ? <Badge variant="destructive">failed</Badge> : null}
          </div>
          {block.status === "failed" ? (
            <p className="text-destructive text-sm">{block.error}</p>
          ) : (
            <TutorialBlockView renderer={block.renderer} payload={block.payload} />
          )}
        </div>
      ))}
    </div>
  );
}
