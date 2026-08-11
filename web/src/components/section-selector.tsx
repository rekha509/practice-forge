"use client";

import { Checkbox } from "@/components/ui/checkbox";
import { Button } from "@/components/ui/button";
import type { SectionSummary } from "@/lib/types";

/** Deliberately a plain vertical list, not a dropdown/combobox — the
 * combobox-style multi-select is what broke first at 375px in testing.
 * A stacked list with real touch-sized rows degrades gracefully because
 * there's nothing to overflow horizontally. */
export function SectionSelector({
  sections,
  selected,
  onChange,
}: {
  sections: SectionSummary[];
  selected: Set<string>;
  onChange: (next: Set<string>) => void;
}) {
  const allSelected = selected.size === sections.length;

  function toggle(id: string) {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    onChange(next);
  }

  return (
    <div>
      <div className="flex items-center justify-between pb-2">
        <p className="text-sm font-medium">
          Chapters{" "}
          <span className="font-normal text-muted-foreground">
            ({allSelected ? "whole book" : `${selected.size} of ${sections.length} selected`})
          </span>
        </p>
        <Button
          type="button"
          variant="link"
          size="sm"
          className="h-auto p-0 text-xs"
          onClick={() => onChange(allSelected ? new Set() : new Set(sections.map((s) => s.id)))}
        >
          {allSelected ? "Select none" : "Select all"}
        </Button>
      </div>
      <div className="max-h-80 space-y-1 overflow-y-auto rounded-md border border-border p-1">
        {sections.map((section) => (
          <label
            key={section.id}
            className="flex min-h-11 cursor-pointer items-center justify-between gap-3 rounded-sm px-2 py-2 hover:bg-secondary/60"
          >
            <span className="flex items-center gap-3 min-w-0">
              <Checkbox
                checked={selected.has(section.id)}
                onCheckedChange={() => toggle(section.id)}
              />
              <span className="truncate text-sm">
                {section.chapter_no !== null ? `${section.chapter_no}. ` : ""}
                {section.title}
              </span>
            </span>
            <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
              {section.problem_count} problems
            </span>
          </label>
        ))}
      </div>
    </div>
  );
}
