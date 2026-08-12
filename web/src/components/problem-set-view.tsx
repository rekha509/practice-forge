"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { CodeBlock } from "@/components/code-block";
import { useAuth } from "@/lib/auth";
import {
  ApiError,
  chatAboutStep,
  codeZipUrl,
  getProblemSet,
  handoutPdfUrl,
  newSetFromProblemSet,
  reshuffleProblemSet,
  solutionsPdfUrl,
} from "@/lib/api";
import type { ProblemSetDetail } from "@/lib/types";

type StepChatState = { question: string; answer: string | null; error: string | null; loading: boolean };
const EMPTY_CHAT: StepChatState = { question: "", answer: null, error: null, loading: false };
function stepKey(problemIndex: number, stepIndex: number): string {
  return `${problemIndex}:${stepIndex}`;
}

export function ProblemSetView({ problemSetId }: { problemSetId: string }) {
  const router = useRouter();
  const { token } = useAuth();
  const [detail, setDetail] = useState<ProblemSetDetail | null>(null);
  const [busy, setBusy] = useState<"reshuffle" | "new-set" | null>(null);
  const [stepChats, setStepChats] = useState<Record<string, StepChatState>>({});

  const load = useCallback(() => {
    getProblemSet(problemSetId).then(setDetail);
  }, [problemSetId]);

  useEffect(() => {
    load();
  }, [load]);

  async function requireToken(): Promise<string | null> {
    if (!token) {
      toast.error("Set your faculty token first", {
        description: "Use the button in the top-right corner.",
      });
      return null;
    }
    return token;
  }

  async function handleReshuffle() {
    const t = await requireToken();
    if (!t) return;
    setBusy("reshuffle");
    try {
      const { job_id } = await reshuffleProblemSet(problemSetId, t);
      router.push(`/jobs/${job_id}`);
    } catch (err) {
      toast.error("Could not reshuffle", {
        description: err instanceof ApiError ? err.message : String(err),
      });
      setBusy(null);
    }
  }

  async function handleNewSet() {
    const t = await requireToken();
    if (!t) return;
    setBusy("new-set");
    try {
      const { job_id } = await newSetFromProblemSet(problemSetId, {}, t);
      router.push(`/jobs/${job_id}`);
    } catch (err) {
      toast.error("Could not start a new set", {
        description: err instanceof ApiError ? err.message : String(err),
      });
      setBusy(null);
    }
  }

  function updateChat(problemIndex: number, stepIndex: number, patch: Partial<StepChatState>) {
    const key = stepKey(problemIndex, stepIndex);
    setStepChats((prev) => ({ ...prev, [key]: { ...(prev[key] ?? EMPTY_CHAT), ...patch } }));
  }

  async function handleAskAboutStep(problemIndex: number, stepIndex: number) {
    const key = stepKey(problemIndex, stepIndex);
    const question = (stepChats[key] ?? EMPTY_CHAT).question.trim();
    if (!question) return;
    updateChat(problemIndex, stepIndex, { loading: true, error: null, answer: null });
    try {
      const { answer } = await chatAboutStep(problemSetId, {
        problem_index: problemIndex,
        step_index: stepIndex,
        question,
      });
      updateChat(problemIndex, stepIndex, { loading: false, answer });
    } catch (err) {
      updateChat(problemIndex, stepIndex, {
        loading: false,
        error: err instanceof ApiError ? err.message : String(err),
      });
    }
  }

  if (!detail) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-10 sm:px-6">
        <Skeleton className="h-8 w-1/2" />
        <Skeleton className="mt-6 h-40 w-full" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-10 sm:px-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">{detail.title}</h1>
        <p className="text-sm text-muted-foreground">
          {detail.problem_count} problems · generated{" "}
          {new Date(detail.created_at).toLocaleString()}
        </p>
      </div>

      <div className="mt-6 flex flex-wrap gap-2">
        <Button variant="outline" nativeButton={false} render={<a href={handoutPdfUrl(detail.id)} />}>
          Download handout PDF
        </Button>
        <Button variant="outline" nativeButton={false} render={<a href={solutionsPdfUrl(detail.id)} />}>
          Download solutions PDF
        </Button>
        <Button variant="outline" nativeButton={false} render={<a href={codeZipUrl(detail.id)} />}>
          Download code.zip
        </Button>
      </div>

      <div className="mt-6 grid gap-4 sm:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Reshuffle</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm text-muted-foreground">
              Same topics, fresh numbers. Doesn&rsquo;t touch your concept
              pool — reshuffle as many times as you want.
            </p>
            <Button
              onClick={handleReshuffle}
              disabled={busy !== null}
              variant="outline"
              className="w-full"
            >
              {busy === "reshuffle" ? "Starting…" : "Reshuffle"}
            </Button>
          </CardContent>
        </Card>
        <Card className="border-primary/40">
          <CardHeader>
            <CardTitle className="text-base">New set</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm text-muted-foreground">
              {detail.problem_count} different topics, permanently drawn from
              this course&rsquo;s pool.{" "}
              <span className="font-medium text-foreground">
                {detail.remaining_concepts} concepts remaining
              </span>{" "}
              in this book after that.
            </p>
            <Button
              onClick={handleNewSet}
              disabled={busy !== null || detail.remaining_concepts === 0}
              variant="default"
              className="w-full"
            >
              {busy === "new-set"
                ? "Starting…"
                : detail.remaining_concepts === 0
                  ? "Pool exhausted"
                  : "Generate new set"}
            </Button>
          </CardContent>
        </Card>
      </div>

      <Separator className="my-10" />

      <div className="space-y-10">
        {detail.problems.map((problem) => (
          <article key={problem.index} id={`problem-${problem.index}`}>
            <div className="flex items-center justify-between gap-2">
              <h2 className="text-lg font-semibold">
                Problem {problem.index}: {problem.name}
              </h2>
              <Badge variant="secondary" className="capitalize">
                {problem.difficulty}
              </Badge>
            </div>

            <div className="statement-prose mt-3 whitespace-pre-wrap">{problem.statement_md}</div>

            <div className="mt-6">
              <h3 className="text-sm font-medium">Solution</h3>
              <ol className="mt-2 space-y-3">
                {problem.solution_steps.map((step, i) => {
                  const stepIndex = i + 1;
                  const chat = stepChats[stepKey(problem.index, stepIndex)] ?? EMPTY_CHAT;
                  return (
                    <li key={i} className="flex items-start justify-between gap-3">
                      <span className="statement-prose whitespace-pre-wrap text-sm">{step}</span>
                      <Popover>
                        <PopoverTrigger
                          render={
                            <Button
                              size="sm"
                              variant="ghost"
                              className="shrink-0 text-xs text-muted-foreground"
                            />
                          }
                        >
                          Explain this
                        </PopoverTrigger>
                        <PopoverContent align="end" className="w-80">
                          <div className="space-y-3">
                            <p className="text-sm font-medium">Ask about this step</p>
                            <form
                              className="flex gap-2"
                              onSubmit={(e) => {
                                e.preventDefault();
                                handleAskAboutStep(problem.index, stepIndex);
                              }}
                            >
                              <Input
                                value={chat.question}
                                onChange={(e) =>
                                  updateChat(problem.index, stepIndex, { question: e.target.value })
                                }
                                placeholder="Why this step?"
                                className="text-sm"
                              />
                              <Button type="submit" size="sm" disabled={chat.loading || !chat.question.trim()}>
                                {chat.loading ? "Asking…" : "Ask"}
                              </Button>
                            </form>
                            {chat.answer && (
                              <p className="statement-prose whitespace-pre-wrap text-sm">{chat.answer}</p>
                            )}
                            {chat.error && (
                              <p className="text-sm text-destructive">{chat.error}</p>
                            )}
                          </div>
                        </PopoverContent>
                      </Popover>
                    </li>
                  );
                })}
              </ol>
            </div>

            <div className="mt-6">
              <h3 className="text-sm font-medium">Solver code</h3>
              <div className="mt-2">
                <CodeBlock code={problem.core_python_code} />
              </div>
            </div>

            {problem.verified_answer && (
              <p className="mt-4 font-mono text-sm">
                <span className="text-muted-foreground">Verified answer: </span>
                {problem.verified_answer}
              </p>
            )}
          </article>
        ))}
      </div>
    </div>
  );
}
