"use client";

/**
 * "Your course's styles": a professor adds a style that only this course uses, written in the
 * same YAML as a library contribution (CONTRIBUTING-styles.md), usually by starting from a
 * library style. The backend runs the library's style checks before saving. Every style can be
 * exported as the file a pull request to the library needs.
 */

import { useState } from "react";
import { QueryError } from "@/components/query-state";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { fetchStyleYaml, useCreateCourseStyle } from "@/lib/api/queries";

type StyleSummary = { id: string; name: string };

export function CourseStyles({
  styles,
  courseStyleIds,
}: {
  styles: readonly StyleSummary[];
  courseStyleIds: readonly string[];
}) {
  const create = useCreateCourseStyle();
  const [text, setText] = useState("");
  const [loadError, setLoadError] = useState<unknown>(null);
  const own = styles.filter((style) => courseStyleIds.includes(style.id));
  const error = create.error ?? loadError;

  async function startFrom(styleId: string) {
    setLoadError(null);
    try {
      setText(await fetchStyleYaml(styleId));
    } catch (failure) {
      setLoadError(failure);
    }
  }

  async function exportStyle(styleId: string) {
    setLoadError(null);
    try {
      const yaml = await fetchStyleYaml(styleId);
      const url = URL.createObjectURL(new Blob([yaml], { type: "application/yaml" }));
      const link = document.createElement("a");
      link.href = url;
      link.download = `${styleId}.yaml`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (failure) {
      setLoadError(failure);
    }
  }

  async function add() {
    try {
      await create.mutateAsync(text);
      setText("");
    } catch {
      // The mutation error, with every failed check, appears below without closing the modal.
    }
  }

  return (
    <details className="mt-6 rounded-lg border p-4">
      <summary className="cursor-pointer font-medium text-sm">
        Your course's styles (optional)
      </summary>
      <div className="mt-3 space-y-3">
        <p className="text-muted-foreground text-sm">
          Add a style only this course uses. It appears with the library styles above and must pass
          the same checks: both examples are run through their question type's checks and grader.
          Export a style to propose it for the shared library.
        </p>
        {error ? <QueryError error={error} /> : null}
        {own.length > 0 ? (
          <ul className="divide-y rounded-md border">
            {own.map((style) => (
              <li key={style.id} className="flex items-center gap-2 px-3 py-2 text-sm">
                <span className="min-w-0 flex-1 truncate">{style.name}</span>
                <code className="text-muted-foreground text-xs">{style.id}</code>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => void exportStyle(style.id)}
                >
                  Export to YAML
                </Button>
              </li>
            ))}
          </ul>
        ) : null}
        <div className="flex flex-wrap items-center gap-2">
          <select
            aria-label="Start from a style"
            value=""
            onChange={(event) => {
              if (event.target.value) void startFrom(event.target.value);
            }}
            className="h-9 rounded-md border bg-background px-2 text-sm"
          >
            <option value="">Start from a style…</option>
            {styles.map((style) => (
              <option key={style.id} value={style.id}>
                {style.name}
              </option>
            ))}
          </select>
          <span className="text-muted-foreground text-xs">
            Then give it a new <code>id</code> and change what you need.
          </span>
        </div>
        <Textarea
          aria-label="New style (YAML)"
          value={text}
          onChange={(event) => setText(event.target.value)}
          rows={14}
          spellCheck={false}
          className="font-mono text-xs"
          placeholder={"id: py.my_style\nname: …"}
        />
        <Button
          type="button"
          variant="outline"
          disabled={!text.trim() || create.isPending}
          onClick={() => void add()}
        >
          {create.isPending ? "Checking…" : "Check and add style"}
        </Button>
      </div>
    </details>
  );
}
