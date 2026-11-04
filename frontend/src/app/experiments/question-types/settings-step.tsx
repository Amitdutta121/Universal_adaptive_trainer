"use client";

/**
 * Stand-in for the question types section of course Settings
 * (`app/courses/question-type-picker.tsx` in the real app): the types this course allows.
 * A new course starts with all of its subject's default types ticked.
 */

import { cn } from "@/lib/utils";
import { type SetupState, type TypeGroup, typeAllowed } from "./setup-model";

export function SettingsStep({
  groups,
  state,
  onAllowed,
}: {
  groups: readonly TypeGroup[];
  state: SetupState;
  onAllowed(typeId: string, allowed: boolean): void;
}) {
  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
      <h3 className="font-semibold text-base">Question types</h3>
      <p className="text-muted-foreground text-sm">Types this course can use.</p>
      <ul className="mt-4 flex max-w-xl flex-col divide-y rounded-lg border">
        {groups.map((group) => {
          const allowed = typeAllowed(state, group.id);
          return (
            <li key={group.id}>
              <label className="flex cursor-pointer items-center gap-3 px-4 py-3">
                <input
                  type="checkbox"
                  className="size-4 accent-[var(--accent-solid)]"
                  checked={allowed}
                  onChange={(event) => onAllowed(group.id, event.target.checked)}
                />
                <span className={cn("mr-auto text-sm", !allowed && "text-muted-foreground")}>
                  {group.label}
                </span>
                <span className="text-muted-foreground text-xs">
                  {group.styles.length} {group.styles.length === 1 ? "style" : "styles"}
                </span>
              </label>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
