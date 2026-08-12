"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { BookOpen } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { UploadDialog } from "@/components/upload-dialog";
import { listBooks } from "@/lib/api";
import type { BookListItem } from "@/lib/types";

const POLL_INTERVAL_MS = 5000;

function statusVariant(status: string): "default" | "secondary" | "outline" {
  if (status === "done") return "default";
  if (status === "failed") return "outline";
  return "secondary";
}

export default function LibraryPage() {
  const [books, setBooks] = useState<BookListItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const result = await listBooks();
        if (!cancelled) {
          setBooks(result);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      }
    }
    load();
    // Books mid-ingest transition status without any user action — a
    // light poll keeps the grid honest without requiring a manual refresh.
    const interval = setInterval(load, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  return (
    <div className="mx-auto max-w-5xl px-4 py-10 sm:px-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Library</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Every textbook ingested by the department. Ingest once, generate
            from it forever.
          </p>
        </div>
        <UploadDialog />
      </div>

      {error && (
        <p className="mt-8 text-sm text-destructive">
          Could not reach the API: {error}
        </p>
      )}

      {books === null && !error && (
        <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-32 w-full" />
          ))}
        </div>
      )}

      {books !== null && books.length === 0 && (
        <div className="mt-16 flex flex-col items-center gap-2 text-center">
          <BookOpen className="size-8 text-muted-foreground/50" aria-hidden="true" />
          <p className="text-sm text-muted-foreground">No textbooks yet. Add one to get started.</p>
        </div>
      )}

      {books !== null && books.length > 0 && (
        <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {books.map((book) => {
            const ready = book.ingest_status === "done";
            const card = (
              <Card
                className={
                  ready
                    ? "border-t-2 border-t-primary shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-md"
                    : "border-t-2 border-t-transparent opacity-70"
                }
              >
                <CardHeader>
                  <div className="flex items-start justify-between gap-2">
                    <CardTitle className="flex items-start gap-2 text-base leading-snug">
                      <BookOpen className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden="true" />
                      {book.title}
                    </CardTitle>
                    <Badge variant={statusVariant(book.ingest_status)} className="shrink-0">
                      {book.ingest_status}
                    </Badge>
                  </div>
                </CardHeader>
                <CardContent className="flex items-center gap-4 text-sm text-muted-foreground">
                  <span>{book.page_count.toLocaleString()} pages</span>
                  <span aria-hidden>·</span>
                  <span>{book.concept_count.toLocaleString()} concepts ready</span>
                </CardContent>
              </Card>
            );
            return ready ? (
              <Link key={book.id} href={`/books/${book.id}/generate`}>
                {card}
              </Link>
            ) : (
              <div key={book.id}>{card}</div>
            );
          })}
        </div>
      )}
    </div>
  );
}
