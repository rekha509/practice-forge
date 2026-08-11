// Mirrors api/schemas.py exactly. Keep in sync by hand — there's no
// shared-schema codegen in this project (Python Pydantic on one side,
// TypeScript on the other), so a drifted field here is a silent bug, not
// a type error, until it surfaces in the UI.

export interface InitiateUploadRequest {
  filename: string;
  total_bytes: number;
  discipline: string;
}

export interface InitiateUploadResponse {
  job_id: string;
  chunk_url: string;
}

export interface BookListItem {
  id: string;
  title: string;
  page_count: number;
  ingest_status: string;
  concept_count: number;
}

export interface SectionSummary {
  id: string;
  chapter_no: number | null;
  title: string;
  page_start: number;
  page_end: number;
  problem_count: number;
}

export interface BookDetail {
  id: string;
  title: string;
  authors: string[];
  page_count: number;
  ingest_status: string;
  sections: SectionSummary[];
}

export interface JobStatusOut {
  id: string;
  kind: "ingest" | "generate" | "reshuffle" | "new_set";
  status: "uploading" | "queued" | "running" | "done" | "failed";
  stage: string;
  pct: number | null;
  bytes_received: number | null;
  bytes_total: number | null;
  pages_done: number | null;
  pages_total: number | null;
  items_done: number | null;
  items_total: number | null;
  eta_seconds: number | null;
  error_message: string | null;
  result_book_id: string | null;
  result_problem_set_id: string | null;
}

export interface GenerateRequest {
  book_id: string;
  course_id: string;
  section_ids?: string[] | null;
  count?: number;
  difficulty_mix?: Record<string, number> | null;
}

export interface NewSetRequest {
  section_ids?: string[] | null;
  count?: number | null;
  difficulty_mix?: Record<string, number> | null;
}

export interface JobAccepted {
  job_id: string;
}

export interface ProblemSetSummary {
  id: string;
  course_id: string;
  title: string;
  run_number: number;
  problem_count: number;
  created_at: string;
  remaining_concepts: number;
}

export interface ProblemPreview {
  index: number;
  name: string;
  statement_md: string;
  difficulty: string;
  solution_steps: string[];
  core_python_code: string;
  verified_answer: string | null;
  extension_type: string;
}

export interface ProblemSetDetail extends ProblemSetSummary {
  problems: ProblemPreview[];
}
