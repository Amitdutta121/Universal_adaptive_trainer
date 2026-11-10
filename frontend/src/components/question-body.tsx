import { PromptText } from "@/components/prompt-text";
import { QuestionFigure } from "@/components/question-figure";
import type { QuestionFigure as Figure } from "@/lib/api/types";
import { cn } from "@/lib/utils";

/** A question as it is read: the prompt, then its figure when it has one. */
export function QuestionBody({
  prompt,
  figure,
  className,
  promptClassName,
}: {
  prompt: string;
  figure?: Figure | null;
  className?: string;
  promptClassName?: string;
}) {
  return (
    <div className={cn("space-y-4", className)}>
      <PromptText text={prompt} className={promptClassName} />
      {figure ? <QuestionFigure figure={figure} /> : null}
    </div>
  );
}
