import type { Metadata } from "next";
import { RecipeBuilder } from "./recipe-builder";

export const metadata: Metadata = { title: "Recipe builder · Adaptive Trainer" };

export default function ExperimentalTutorialPage() {
  return <RecipeBuilder />;
}
