import ReactMarkdown from "react-markdown";

/**
 * A markdown tutorial block. react-markdown builds React elements and drops raw html
 * (`skipHtml`); images are not rendered, so a block never loads anything from the network.
 */
export function MarkdownBlock({ markdown }: { markdown: string }) {
  return (
    <div className="space-y-2 text-sm leading-relaxed [&_code]:rounded [&_code]:bg-muted [&_code]:px-1 [&_code]:font-mono [&_pre]:overflow-x-auto [&_pre]:rounded-md [&_pre]:border [&_pre]:bg-muted/40 [&_pre]:p-3 [&_pre_code]:bg-transparent [&_pre_code]:p-0">
      <ReactMarkdown skipHtml disallowedElements={["img"]}>
        {markdown}
      </ReactMarkdown>
    </div>
  );
}
