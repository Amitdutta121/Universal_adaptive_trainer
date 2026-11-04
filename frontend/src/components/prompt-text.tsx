import "katex/dist/katex.min.css";
import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import { cn } from "@/lib/utils";

/**
 * Renders a question prompt as light Markdown: inline code, fenced code, bullet and numbered
 * lists, GFM tables and `$…$` / `$$…$$` math. Raw html is dropped (`skipHtml`) and images are not
 * rendered, so a prompt cannot inject markup or load anything. Plain-text prompts render as before.
 *
 * `variant="preview"` is for clamped one- or two-line rows (tables, lists): the Markdown is
 * flattened to a single line, code blocks become `[code]`, tables `[table]`, display math `[formula]`.
 */
export function PromptText({
  text,
  variant = "full",
  className,
}: {
  text: string;
  variant?: "full" | "preview";
  className?: string;
}) {
  if (variant === "preview") {
    return (
      <span className={cn("line-clamp-2 text-[0.8rem] leading-5", className)}>
        {previewSegments(text).map((segment, index) =>
          segment.code ? (
            // biome-ignore lint/suspicious/noArrayIndexKey: static derived segments
            <code key={index} className="font-mono text-[0.92em]">
              {segment.text}
            </code>
          ) : (
            // biome-ignore lint/suspicious/noArrayIndexKey: static derived segments
            <span key={index} className={segment.muted ? "text-muted-foreground" : undefined}>
              {segment.text}
            </span>
          ),
        )}
      </span>
    );
  }

  return (
    <div
      className={cn(
        "space-y-3 text-foreground leading-7",
        "[&_code]:rounded [&_code]:bg-muted [&_code]:px-1 [&_code]:py-px [&_code]:font-mono [&_code]:text-[0.88em]",
        "[&_pre]:overflow-x-auto [&_pre]:rounded-md [&_pre]:border [&_pre]:border-border [&_pre]:bg-muted/40 [&_pre]:px-3 [&_pre]:py-2.5 [&_pre]:leading-6",
        "[&_pre_code]:bg-transparent [&_pre_code]:p-0",
        "[&_ol]:list-decimal [&_ol]:space-y-1 [&_ol]:pl-5 [&_ul]:list-disc [&_ul]:space-y-1 [&_ul]:pl-5",
        "[&_table]:w-auto [&_table]:border-collapse [&_table]:text-sm [&_td]:border [&_td]:border-border [&_td]:px-2.5 [&_td]:py-1 [&_th]:border [&_th]:border-border [&_th]:bg-muted/50 [&_th]:px-2.5 [&_th]:py-1 [&_th]:text-left [&_th]:font-medium",
        "[&_.katex-display]:my-2 [&_.katex-display]:overflow-x-auto [&_.katex-display]:py-1",
        "[&_blockquote]:border-border [&_blockquote]:border-l-2 [&_blockquote]:pl-3 [&_blockquote]:text-muted-foreground",
        className,
      )}
    >
      <ReactMarkdown
        skipHtml
        disallowedElements={["img"]}
        remarkPlugins={[remarkGfm, [remarkMath, { singleDollarTextMath: true }]]}
        rehypePlugins={[rehypeKatex]}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}

/** Private-use characters that never appear in prompts; they delimit placeholder segments. */
const MARK = "";
const ROW = "";

type Segment ={ text: string; code?: boolean; muted?: boolean };

/** Flattens Markdown to one line of segments for clamped previews. Exported for tests. */
export function previewSegments(text: string): Segment[] {
  const flat = text
    .replace(/```[\s\S]*?```/g, ` ${MARK}[code]${MARK} `)
    .replace(/\$\$[\s\S]*?\$\$/g, ` ${MARK}[formula]${MARK} `)
    .replace(/(^|\n)\s*\|.*\|(?=\n|$)/g, ROW)
    .replace(new RegExp(`${ROW}+`, "g"), ` ${MARK}[table]${MARK} `)
    .replace(/\*\*(.+?)\*\*/g, "$1")
    .replace(/(^|\n)\s*(?:[-*]|\d+\.)\s+/g, "$1")
    .replace(/\$([^$\n]+)\$/g, "$1")
    .replace(/\s+/g, " ")
    .trim();

  const segments: Segment[] = [];
  for (const [index, part] of flat.split(MARK).entries()) {
    if (!part) continue;
    if (index % 2 === 1) {
      segments.push({ text: part, muted: true });
      continue;
    }
    for (const [inner, piece] of part.split("`").entries()) {
      if (piece) segments.push({ text: piece, code: inner % 2 === 1 });
    }
  }
  return segments;
}
