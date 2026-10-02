/** A copyable shell snippet. Lines starting with `#` render as muted comments. */

import { CopyButton } from "@/components/copy-button";

export function CommandBlock({ label, code }: { label: string; code: string }) {
  const lines = code.split("\n");
  return (
    <div className="overflow-hidden rounded-lg border border-border bg-muted">
      <div className="flex items-center justify-between border-border border-b px-3 py-1.5">
        <span className="font-mono text-muted-foreground text-xs">
          {label}
        </span>
        <CopyButton text={code} size="xs" variant="ghost" />
      </div>
      <pre className="overflow-x-auto px-3 py-3 font-mono text-[0.8rem] leading-6">
        {lines.map((line, index) => (
          // biome-ignore lint/suspicious/noArrayIndexKey: static, never reordered
          <div key={index} className={line.startsWith("#") ? "text-muted-foreground" : undefined}>
            {line || " "}
          </div>
        ))}
      </pre>
    </div>
  );
}
