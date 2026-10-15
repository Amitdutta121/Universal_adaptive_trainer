"use client";

/**
 * Tutorial blocks for one subtopic of the approved taxonomy (Phase 5).
 *
 * Pick a subtopic, a recipe (`GET /api/tutorial-recipes`) and a guidance level the recipe
 * supports, then generate one block (`POST /api/tutorial-blocks`): one model call plus the
 * recipe's tool and checks. The subtopic's blocks (`GET /api/tutorial-blocks`) render below
 * exactly as a student would see them, each with the chunks it was written from; a failed block
 * shows why. Above it, the taxonomy's blocks are pre-generated as one job and approved by
 * recipe (`recipe-approval.tsx`, Phase 6).
 */

import { useState } from "react";
import { toast } from "sonner";
import { EmptyState, QueryError, TableSkeleton } from "@/components/query-state";
import { TutorialBlockView } from "@/components/tutorial/renderer-registry";
import type { TutorialBlock } from "@/components/tutorial/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  useApprovedCurriculum,
  useGenerateTutorialBlock,
  useTutorialBlocks,
  useTutorialRecipes,
} from "@/lib/api/queries";
import type { Schemas } from "@/lib/api/types";
import { RecipeApproval } from "./recipe-approval";

type GuidanceLevel = Schemas["GuidanceLevel"];

const LEVEL_LABELS: Record<GuidanceLevel, string> = {
  worked: "Worked (full explanation)",
  faded: "Faded (last steps left to the student)",
  cue: "Cue (a short reminder)",
};

export function TutorialsScreen() {
  const approved = useApprovedCurriculum();
  const recipes = useTutorialRecipes();
  const [subtopicId, setSubtopicId] = useState<number | null>(null);
  const [recipeId, setRecipeId] = useState<string | null>(null);
  const [level, setLevel] = useState<GuidanceLevel | null>(null);
  const blocks = useTutorialBlocks(subtopicId);
  const generate = useGenerateTutorialBlock();

  if (approved.isPending || recipes.isPending) return <TableSkeleton rows={3} />;
  if (approved.isError) {
    return (
      <EmptyState
        title="No approved taxonomy yet"
        hint="Tutorial blocks are written per subtopic. Approve a taxonomy under Curriculum first."
      />
    );
  }
  if (recipes.isError) return <QueryError error={recipes.error} />;

  const recipe = recipes.data.recipes.find((item) => item.id === recipeId) ?? null;
  const recipeNames = new Map(recipes.data.recipes.map((item) => [item.id, item.name]));
  const ready = subtopicId !== null && recipe !== null && level !== null;

  function chooseRecipe(id: string) {
    setRecipeId(id);
    const next = recipes.data?.recipes.find((item) => item.id === id);
    if (next && level !== null && !next.guidance_levels.includes(level)) setLevel(null);
  }

  async function handleGenerate() {
    if (!ready) return;
    try {
      const block = await generate.mutateAsync({
        subtopic_id: subtopicId,
        recipe_id: recipe.id,
        guidance_level: level,
      });
      if (block.status === "failed") {
        toast.error("The block failed its checks", { description: block.error ?? undefined });
      } else {
        toast.success(`${recipe.name}: block ready`);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "Could not generate the block.";
      toast.error("Could not generate the block", { description: message });
    }
  }

  return (
    <div className="space-y-6">
      <RecipeApproval versionId={approved.data.version.id} />
      <Card>
        <CardHeader>
          <CardTitle>Generate a block</CardTitle>
          <CardDescription>
            Written from the subtopic's book chunks with one model call. Code steppers show a
            recorded run of the code, and every html block is loaded in a headless browser before it
            is saved.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-[2fr_2fr_2fr_auto] md:items-end">
          <div className="space-y-1.5">
            <Label htmlFor="tutorial-subtopic">Subtopic</Label>
            <Select
              value={subtopicId === null ? "" : String(subtopicId)}
              onValueChange={(value) => setSubtopicId(Number(value))}
            >
              <SelectTrigger id="tutorial-subtopic" className="w-full">
                <SelectValue placeholder="Choose a subtopic" />
              </SelectTrigger>
              <SelectContent>
                {approved.data.topics.map((topic) => (
                  <SelectGroup key={topic.id}>
                    <SelectLabel>{topic.name}</SelectLabel>
                    {topic.subtopics.map((subtopic) => (
                      <SelectItem key={subtopic.id} value={String(subtopic.id)}>
                        {subtopic.name}
                      </SelectItem>
                    ))}
                  </SelectGroup>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="tutorial-recipe">Recipe</Label>
            <Select value={recipeId ?? ""} onValueChange={chooseRecipe}>
              <SelectTrigger id="tutorial-recipe" className="w-full">
                <SelectValue placeholder="Choose a recipe" />
              </SelectTrigger>
              <SelectContent>
                {recipes.data.recipes.map((item) => (
                  <SelectItem key={item.id} value={item.id}>
                    {item.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="tutorial-level">Guidance</Label>
            <Select
              value={level ?? ""}
              onValueChange={(value) => setLevel(value as GuidanceLevel)}
              disabled={recipe === null}
            >
              <SelectTrigger id="tutorial-level" className="w-full">
                <SelectValue placeholder="Choose a level" />
              </SelectTrigger>
              <SelectContent>
                {(recipe?.guidance_levels ?? []).map((item) => (
                  <SelectItem key={item} value={item}>
                    {LEVEL_LABELS[item]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Button onClick={handleGenerate} disabled={!ready || generate.isPending}>
            {generate.isPending ? "Generating…" : "Generate"}
          </Button>
          {recipe ? (
            <p className="text-muted-foreground text-sm md:col-span-4">{recipe.summary}</p>
          ) : null}
        </CardContent>
      </Card>

      {subtopicId === null ? (
        <EmptyState title="Choose a subtopic" hint="Its tutorial blocks are listed here." />
      ) : blocks.isPending ? (
        <TableSkeleton rows={2} />
      ) : blocks.isError ? (
        <QueryError error={blocks.error} />
      ) : blocks.data.length === 0 ? (
        <EmptyState title="No blocks yet" hint="Generate one above." />
      ) : (
        <div className="space-y-4">
          {blocks.data.map((block) => (
            <BlockCard key={block.id} block={block} recipeName={recipeNames.get(block.recipe_id)} />
          ))}
        </div>
      )}
    </div>
  );
}

function BlockCard({ block, recipeName }: { block: TutorialBlock; recipeName?: string }) {
  return (
    <Card>
      <CardHeader className="gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <CardTitle className="text-base">{recipeName ?? block.recipe_id}</CardTitle>
          <Badge variant="outline">{block.guidance_level}</Badge>
          <Badge variant={block.status === "failed" ? "destructive" : "secondary"}>
            {block.status}
          </Badge>
          <span className="ml-auto text-muted-foreground text-xs">{block.model}</span>
        </div>
        <CardDescription>
          From {block.chunk_ids.length} chunk{block.chunk_ids.length === 1 ? "" : "s"}:{" "}
          <span className="font-mono text-xs">
            {block.chunk_ids.map((chunkId) => chunkId.slice(0, 8)).join(", ")}
          </span>
        </CardDescription>
      </CardHeader>
      <CardContent>
        {block.status === "failed" ? (
          <p className="text-destructive text-sm">{block.error}</p>
        ) : (
          <TutorialBlockView renderer={block.renderer} payload={block.payload} />
        )}
      </CardContent>
    </Card>
  );
}
