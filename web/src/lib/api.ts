import type {
  BookDetail,
  BookListItem,
  GenerateRequest,
  InitiateUploadResponse,
  JobAccepted,
  JobStatusOut,
  NewSetRequest,
  ProblemSetDetail,
  ProblemSetSummary,
} from "./types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(
  path: string,
  init?: RequestInit & { token?: string | null }
): Promise<T> {
  const { token, headers, ...rest } = init ?? {};
  const res = await fetch(`${API_BASE}${path}`, {
    ...rest,
    headers: {
      ...(rest.body && !(rest.body instanceof ArrayBuffer) && !(rest.body instanceof Blob)
        ? { "Content-Type": "application/json" }
        : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...headers,
    },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? JSON.stringify(body);
    } catch {
      // response wasn't JSON — keep statusText
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// --- Books / library / upload ---------------------------------------

export function listBooks(): Promise<BookListItem[]> {
  return request("/api/books");
}

export function getBook(bookId: string): Promise<BookDetail> {
  return request(`/api/books/${bookId}`);
}

export interface UploadProgress {
  bytesUploaded: number;
  totalBytes: number;
}

const CHUNK_SIZE = 4 * 1024 * 1024; // 4 MiB

/** Resumable chunked upload (tus-core-subset — see api/routers/books.py).
 * Returns the ingest job_id once the whole file has been transferred and
 * the server has enqueued ingestion; callers watch that job via SSE for
 * actual ingest progress, separate from this upload-transfer progress. */
export async function uploadBook(
  file: File,
  discipline: string,
  onProgress?: (p: UploadProgress) => void
): Promise<string> {
  const init = await request<InitiateUploadResponse>("/api/books", {
    method: "POST",
    body: JSON.stringify({
      filename: file.name,
      total_bytes: file.size,
      discipline,
    }),
  });

  let offset = 0;
  while (offset < file.size) {
    const end = Math.min(offset + CHUNK_SIZE, file.size);
    const chunk = await file.slice(offset, end).arrayBuffer();
    const res = await fetch(`${API_BASE}${init.chunk_url}`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/offset+octet-stream",
        "Upload-Offset": String(offset),
      },
      body: chunk,
    });
    if (!res.ok) {
      throw new ApiError(res.status, `chunk upload failed at offset ${offset}`);
    }
    offset = Number(res.headers.get("Upload-Offset") ?? end);
    onProgress?.({ bytesUploaded: offset, totalBytes: file.size });
  }

  return init.job_id;
}

// --- Jobs -------------------------------------------------------------

export function getJob(jobId: string): Promise<JobStatusOut> {
  return request(`/api/jobs/${jobId}`);
}

export function jobStreamUrl(jobId: string): string {
  return `${API_BASE}/api/jobs/${jobId}/stream`;
}

// --- Problem sets -------------------------------------------------------

export function generateProblemSet(
  req: GenerateRequest,
  token: string
): Promise<JobAccepted> {
  return request("/api/problem-sets", {
    method: "POST",
    body: JSON.stringify(req),
    token,
  });
}

export function listProblemSets(courseId: string): Promise<ProblemSetSummary[]> {
  return request(`/api/problem-sets?course_id=${courseId}`);
}

export function getProblemSet(id: string): Promise<ProblemSetDetail> {
  return request(`/api/problem-sets/${id}`);
}

export function reshuffleProblemSet(id: string, token: string): Promise<JobAccepted> {
  return request(`/api/problem-sets/${id}/reshuffle`, { method: "POST", token });
}

export function newSetFromProblemSet(
  id: string,
  req: NewSetRequest,
  token: string
): Promise<JobAccepted> {
  return request(`/api/problem-sets/${id}/new-set`, {
    method: "POST",
    body: JSON.stringify(req),
    token,
  });
}

export function handoutPdfUrl(id: string): string {
  return `${API_BASE}/api/problem-sets/${id}/handout.pdf`;
}

export function solutionsPdfUrl(id: string): string {
  return `${API_BASE}/api/problem-sets/${id}/solutions.pdf`;
}

export function codeZipUrl(id: string): string {
  return `${API_BASE}/api/problem-sets/${id}/code.zip`;
}
