"use client";

import { useEffect, useState } from "react";
import { jobStreamUrl } from "./api";
import type { JobStatusOut } from "./types";

/** Live SSE job status. Safe to mount/unmount freely — a fresh
 * EventSource just reconnects and the server immediately re-emits the
 * job's CURRENT state (it polls JobORM, not an in-memory stream), so
 * closing and reopening a tab mid-job picks up exactly where the real
 * progress is, not where the tab last saw it. */
export function useJobStream(jobId: string | null): {
  status: JobStatusOut | null;
  connectionError: boolean;
} {
  // Keyed by jobId rather than reset via an effect-body setState: the
  // returned `status` is DERIVED (jobId ? byJobId[jobId] ?? null : null)
  // instead of a separately-reset "current status" field, so there's
  // nothing to clear when jobId changes — it just naturally reads null
  // for a jobId that hasn't reported anything yet.
  const [byJobId, setByJobId] = useState<Record<string, JobStatusOut>>({});
  const [connectionError, setConnectionError] = useState(false);

  useEffect(() => {
    if (!jobId) return;

    const source = new EventSource(jobStreamUrl(jobId));

    source.addEventListener("progress", (event) => {
      setConnectionError(false);
      try {
        const payload: JobStatusOut = JSON.parse((event as MessageEvent).data);
        setByJobId((prev) => ({ ...prev, [jobId]: payload }));
        if (payload.status === "done" || payload.status === "failed") {
          // The server closes the stream once terminal; without this,
          // EventSource's built-in auto-reconnect would immediately
          // re-open a new connection to a job that will always close
          // again right away — an infinite reconnect loop for no reason.
          source.close();
        }
      } catch {
        // malformed frame — wait for the next one rather than crash the UI
      }
    });

    source.addEventListener("error", () => {
      setConnectionError(true);
    });

    return () => source.close();
  }, [jobId]);

  return { status: jobId ? (byJobId[jobId] ?? null) : null, connectionError };
}
