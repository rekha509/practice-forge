"use client";

import Link from "next/link";
import { CheckCircle2, Circle, LoaderCircle, XCircle } from "lucide-react";
import { useJobStream } from "@/lib/use-job-stream";
import { Progress } from "@/components/ui/progress";
import { Button } from "@/components/ui/button";
import type { JobStatusOut } from "@/lib/types";

function formatEta(seconds: number | null): string | null {
  if (seconds === null) return null;
  if (seconds < 60) return `${Math.round(seconds)}s remaining`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min remaining`;
  const hours = (minutes / 60).toFixed(1);
  return `${hours} hr remaining`;
}

type StepState = "done" | "active" | "pending" | "failed";

function Step({ label, state, detail }: { label: string; state: StepState; detail?: string }) {
  const icon =
    state === "done" ? (
      <CheckCircle2 className="size-5 text-primary" />
    ) : state === "active" ? (
      <LoaderCircle className="size-5 animate-spin text-primary" />
    ) : state === "failed" ? (
      <XCircle className="size-5 text-destructive" />
    ) : (
      <Circle className="size-5 text-muted-foreground" />
    );
  return (
    <div className="flex items-center gap-3">
      {icon}
      <div>
        <p className={state === "pending" ? "text-muted-foreground" : ""}>{label}</p>
        {detail && <p className="text-xs text-muted-foreground">{detail}</p>}
      </div>
    </div>
  );
}

function stepState(
  status: JobStatusOut,
  stageName: string,
  stagesInOrder: string[]
): StepState {
  if (status.status === "failed") {
    return status.stage === stageName ? "failed" : "pending";
  }
  if (status.status === "done") return "done";
  const currentIdx = stagesInOrder.indexOf(status.stage);
  const thisIdx = stagesInOrder.indexOf(stageName);
  if (currentIdx === -1 || thisIdx === -1) return "pending";
  if (thisIdx < currentIdx) return "done";
  if (thisIdx === currentIdx) return "active";
  return "pending";
}

function IngestSteps({ status }: { status: JobStatusOut }) {
  const order = ["uploading", "extracting"];
  const pagesDetail =
    status.pages_done !== null && status.pages_total !== null
      ? `${status.pages_done.toLocaleString()} / ${status.pages_total.toLocaleString()} pages${
          formatEta(status.eta_seconds) ? ` · ${formatEta(status.eta_seconds)}` : ""
        }`
      : undefined;
  return (
    <>
      <Step label="Upload" state="done" />
      <Step label="Extract pages" state={stepState(status, "extracting", order)} detail={pagesDetail} />
      <Step
        label="Ready in library"
        state={status.status === "done" ? "done" : status.status === "failed" ? "failed" : "pending"}
      />
    </>
  );
}

function GenerateSteps({ status }: { status: JobStatusOut }) {
  const order = ["s7_selection", "s8_s9_generation", "rendering"];
  const itemsDetail =
    status.items_done !== null && status.items_total !== null
      ? `${status.items_done} / ${status.items_total} problems verified`
      : undefined;
  return (
    <>
      <Step label="Select concepts" state={stepState(status, "s7_selection", order)} />
      <Step
        label="Generate & verify"
        state={stepState(status, "s8_s9_generation", order)}
        detail={itemsDetail}
      />
      <Step label="Render PDFs" state={stepState(status, "rendering", order)} />
    </>
  );
}

export function JobProgressView({ jobId }: { jobId: string }) {
  const { status, connectionError } = useJobStream(jobId);

  if (!status) {
    return (
      <div className="mx-auto max-w-lg px-4 py-16 text-center sm:px-6">
        <LoaderCircle className="mx-auto size-6 animate-spin text-muted-foreground" />
        <p className="mt-4 text-sm text-muted-foreground">
          {connectionError ? "Reconnecting…" : "Connecting to job…"}
        </p>
      </div>
    );
  }

  const isIngest = status.kind === "ingest";

  return (
    <div className="mx-auto max-w-lg px-4 py-16 sm:px-6">
      <h1 className="text-xl font-semibold tracking-tight">
        {isIngest ? "Ingest progress" : "Generating problem set"}
      </h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Safe to close this tab — reopen it any time and the real progress
        picks up exactly where it is.
      </p>

      <div className="mt-8 space-y-5">
        {isIngest ? <IngestSteps status={status} /> : <GenerateSteps status={status} />}
      </div>

      {status.pct !== null && status.status === "running" && (
        <Progress value={status.pct} className="mt-6" />
      )}

      {status.status === "failed" && (
        <p className="mt-6 rounded-md bg-destructive/10 p-3 text-sm text-destructive">
          {status.error_message ?? "The job failed for an unknown reason."}
        </p>
      )}

      {status.status === "done" && isIngest && status.result_book_id && (
        <div className="mt-8 flex gap-3">
          <Button nativeButton={false} render={<Link href={`/books/${status.result_book_id}/generate`} />}>
            Generate a problem set
          </Button>
          <Button variant="outline" nativeButton={false} render={<Link href="/" />}>
            Back to library
          </Button>
        </div>
      )}

      {status.status === "done" && !isIngest && status.result_problem_set_id && (
        <div className="mt-8">
          <Button
            nativeButton={false}
            render={<Link href={`/problem-sets/${status.result_problem_set_id}`} />}
          >
            View problem set
          </Button>
        </div>
      )}
    </div>
  );
}
