"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { SectionSelector } from "@/components/section-selector";
import { useAuth } from "@/lib/auth";
import { getBook, generateProblemSet, ApiError } from "@/lib/api";
import type { BookDetail } from "@/lib/types";
import { DIFFICULTY_PRESETS, difficultyMixFor, type DifficultyPreset } from "@/lib/difficulty";

export function GeneratorView({ bookId }: { bookId: string }) {
  const router = useRouter();
  const { token } = useAuth();
  const [book, setBook] = useState<BookDetail | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [count, setCount] = useState(20);
  const [preset, setPreset] = useState<DifficultyPreset>("balanced");
  const [courseId, setCourseId] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    getBook(bookId).then((b) => {
      setBook(b);
      setSelected(new Set(b.sections.map((s) => s.id))); // default: whole book
    });
  }, [bookId]);

  const totalAvailable = book?.sections.reduce((sum, s) => sum + s.problem_count, 0) ?? 0;
  const wholeBook = book !== null && selected.size === book.sections.length;

  async function handleGenerate() {
    if (!token) {
      toast.error("Set your faculty token first", {
        description: "Use the button in the top-right corner.",
      });
      return;
    }
    if (!courseId.trim()) {
      toast.error("Enter a course ID");
      return;
    }
    setSubmitting(true);
    try {
      const { job_id } = await generateProblemSet(
        {
          book_id: bookId,
          course_id: courseId.trim(),
          section_ids: wholeBook ? null : Array.from(selected),
          count,
          difficulty_mix: difficultyMixFor(preset, count),
        },
        token
      );
      router.push(`/jobs/${job_id}`);
    } catch (err) {
      toast.error("Could not start generation", {
        description: err instanceof ApiError ? err.message : String(err),
      });
    } finally {
      setSubmitting(false);
    }
  }

  if (!book) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-10 sm:px-6">
        <Skeleton className="h-8 w-2/3" />
        <Skeleton className="mt-6 h-64 w-full" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl px-4 py-10 sm:px-6">
      <h1 className="text-2xl font-semibold tracking-tight">{book.title}</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        {totalAvailable.toLocaleString()} concepts available across{" "}
        {book.sections.length} chapters.
      </p>

      <div className="mt-8 space-y-8">
        <SectionSelector sections={book.sections} selected={selected} onChange={setSelected} />

        <div className="grid gap-2">
          <div className="flex items-center justify-between">
            <Label htmlFor="count-slider">Problem count</Label>
            <span className="text-sm tabular-nums text-muted-foreground">{count}</span>
          </div>
          <Slider
            id="count-slider"
            min={1}
            max={40}
            step={1}
            value={count}
            onValueChange={(v) => setCount(Array.isArray(v) ? v[0] : v)}
          />
        </div>

        <div className="grid gap-2">
          <Label>Difficulty</Label>
          <Select value={preset} onValueChange={(v) => v && setPreset(v as DifficultyPreset)}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {DIFFICULTY_PRESETS.map((p) => (
                <SelectItem key={p.value} value={p.value}>
                  {p.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="grid gap-2">
          <Label htmlFor="course-id">Course ID</Label>
          <Input
            id="course-id"
            value={courseId}
            onChange={(e) => setCourseId(e.target.value)}
            placeholder="paste your course's ID"
          />
          <p className="text-xs text-muted-foreground">
            Course setup isn&rsquo;t self-service yet — your administrator
            provisions this alongside your faculty token.
          </p>
        </div>

        <Button size="lg" onClick={handleGenerate} disabled={submitting} className="w-full sm:w-auto">
          {submitting ? "Starting…" : "Generate"}
        </Button>
      </div>
    </div>
  );
}
