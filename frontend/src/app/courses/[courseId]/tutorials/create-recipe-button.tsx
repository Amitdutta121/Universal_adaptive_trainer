"use client";

/** "Create a recipe" in the tutorials header: opens the recipe builder in a modal. */

import { Plus } from "lucide-react";
import { useState } from "react";
import { RecipeEditorDialog } from "@/app/experimental_tutorial/recipe-builder";
import { Button } from "@/components/ui/button";
import { useCourseId } from "@/lib/use-course";

export function CreateRecipeButton() {
  const courseId = useCourseId();
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button size="sm" className="h-9" onClick={() => setOpen(true)}>
        <Plus data-icon="inline-start" />
        Create a recipe
      </Button>
      {open ? (
        <RecipeEditorDialog courseId={courseId} recipe={null} onClose={() => setOpen(false)} />
      ) : null}
    </>
  );
}
