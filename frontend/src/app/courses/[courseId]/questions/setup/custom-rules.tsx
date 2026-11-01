"use client";

import { useState } from "react";
import { QueryError } from "@/components/query-state";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useCreateCustomJudge, useCustomJudges, useUpdateCustomJudge } from "@/lib/api/queries";
import type { CustomJudge } from "@/lib/api/types";

export function CustomRules({ curriculumVersionId }: { curriculumVersionId: number }) {
  const rules = useCustomJudges(curriculumVersionId);
  const create = useCreateCustomJudge();
  const update = useUpdateCustomJudge();
  const [text, setText] = useState("");
  const [kind, setKind] = useState<"llm" | "pattern">("llm");
  const [pattern, setPattern] = useState("");
  const error = rules.error ?? create.error ?? update.error;

  async function add() {
    try {
      await create.mutateAsync({
        curriculum_version_id: curriculumVersionId,
        rule_text: text.trim(),
        kind,
        enabled: true,
        pattern: kind === "pattern" ? pattern.trim() : null,
      });
      setText("");
      setPattern("");
    } catch {
      // The mutation error appears below without closing the setup modal.
    }
  }

  return (
    <details className="mt-6 rounded-lg border p-4">
      <summary className="cursor-pointer font-medium text-sm">Custom rules (optional)</summary>
      <div className="mt-3 space-y-3">
        <p className="text-muted-foreground text-sm">
          Every generated question must follow your enabled rules. Rules are saved for this
          taxonomy.
        </p>
        {error ? <QueryError error={error} /> : null}
        {rules.isPending ? <p role="status">Loading rules…</p> : null}
        {rules.data?.judges.map((rule) => (
          <RuleRow
            key={rule.id}
            rule={rule}
            pending={update.isPending}
            onSave={async (ruleText, enabled) => {
              await update.mutateAsync({
                judgeId: rule.id,
                body: { rule_text: ruleText, enabled },
              });
            }}
          />
        ))}
        <div className="flex flex-wrap items-center gap-2">
          <Input
            aria-label="New custom rule"
            placeholder="For example: avoid global variables"
            value={text}
            onChange={(event) => setText(event.target.value)}
            maxLength={2000}
            className="min-w-56 flex-1"
          />
          <select
            aria-label="Rule check"
            value={kind}
            onChange={(event) => setKind(event.target.value as "llm" | "pattern")}
            className="h-9 rounded-md border bg-background px-2 text-sm"
          >
            <option value="llm">AI check</option>
            <option value="pattern">Forbidden code pattern</option>
          </select>
          {kind === "pattern" ? (
            <Input
              aria-label="Forbidden pattern"
              placeholder="Regex, or ast:Global"
              value={pattern}
              onChange={(event) => setPattern(event.target.value)}
              className="min-w-48"
            />
          ) : null}
          <Button
            type="button"
            variant="outline"
            disabled={!text.trim() || (kind === "pattern" && !pattern.trim()) || create.isPending}
            onClick={() => void add()}
          >
            {create.isPending ? "Adding…" : "Add rule"}
          </Button>
        </div>
      </div>
    </details>
  );
}

function RuleRow({
  rule,
  pending,
  onSave,
}: {
  rule: CustomJudge;
  pending: boolean;
  onSave: (text: string, enabled: boolean) => Promise<void>;
}) {
  const [text, setText] = useState(rule.rule_text);
  async function save(enabled: boolean) {
    try {
      await onSave(text.trim(), enabled);
    } catch {
      // The parent renders the mutation error.
    }
  }
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Input
        aria-label={`Rule ${rule.id}`}
        value={text}
        onChange={(event) => setText(event.target.value)}
        maxLength={2000}
        className="min-w-56 flex-1"
      />
      <span className="text-muted-foreground text-xs">{rule.enabled ? "Enabled" : "Disabled"}</span>
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={pending || !text.trim() || text === rule.rule_text}
        onClick={() => void save(rule.enabled)}
      >
        Save rule
      </Button>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        disabled={pending || !text.trim()}
        onClick={() => void save(!rule.enabled)}
      >
        {rule.enabled ? "Disable" : "Enable"}
      </Button>
    </div>
  );
}
