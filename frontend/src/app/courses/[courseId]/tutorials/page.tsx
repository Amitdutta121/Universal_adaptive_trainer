/**
 * The tutorials route: the course's tutorial recipes, and making new ones
 * (`/api/tutorial-recipes`, `/api/experimental/recipes`).
 */

import { PageHeader } from "@/components/page-header";
import { SECTIONS_BY_KEY } from "@/lib/navigation";
import { CreateRecipeButton } from "./create-recipe-button";
import { TutorialsScreen } from "./tutorials-screen";

export default function TutorialsPage() {
  const section = SECTIONS_BY_KEY.tutorials;
  return (
    <div className="space-y-6 pb-16">
      <PageHeader
        title={section.label}
        summary={section.summary}
        actions={<CreateRecipeButton />}
      />
      <TutorialsScreen />
    </div>
  );
}
