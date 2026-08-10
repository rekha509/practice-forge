"""`pf` — the practice-forge CLI.

`generate` is a stub until S6-S10 land (Phases P6-P10); `profiles` and
`ingest` are fully functional.
"""

from __future__ import annotations

import getpass
import logging
import uuid
from pathlib import Path

import typer
from sqlalchemy import select as sa_select

from practice_forge.codegen.codegen import generate_and_verify_solution
from practice_forge.concepts.concepts import run_concept_distillation
from practice_forge.db.base import session_scope
from practice_forge.db.models import BookORM, DisciplineORM, SourceProblemORM, VariantORM
from practice_forge.detection.detection import make_default_batch_confirm_fn
from practice_forge.detection.detection import run_detection as run_detection_
from practice_forge.figures.figures import run_figure_descope
from practice_forge.ingest.pipeline import run_ingest
from practice_forge.llm.client import LLMClient
from practice_forge.models.enums import VerificationStatus
from practice_forge.profiles.loader import list_profiles, load_profile
from practice_forge.profiles.sync import sync_disciplines, sync_topic_nodes
from practice_forge.render.render import run_render
from practice_forge.scoring.scoring import run_scoring
from practice_forge.selection.selection import run_selection
from practice_forge.structure.structure import run_structure
from practice_forge.variants.variants import generate_variant, select_extension_attachments
from practice_forge.verification.calibration import run_calibration

app = typer.Typer(name="pf", help="Generate execution-verified engineering practice problem sets.")
profiles_app = typer.Typer(help="Inspect discipline profiles.")
app.add_typer(profiles_app, name="profiles")

_LLM_USAGE_LOG_PATH = Path(__file__).resolve().parents[3] / "data" / "llm_usage.log"


def _configure_logging() -> None:
    """Every real `pf` command that calls the LLM emits one structured JSON
    line per request via `practice_forge.llm.client`'s logger
    (job_id/stage/provider/model/tokens/cost/requests_used_today). Without
    this, that logger's INFO records are silently dropped (root default is
    WARNING) — found live: most of this session's real per-stage token
    counts were never durably captured because of exactly this gap. Two
    sinks: stderr for interactive visibility, and an appended JSONL file so
    a multi-day, multi-invocation ingest can be aggregated for a usage
    report afterward."""
    logging.basicConfig(level=logging.WARNING)
    llm_logger = logging.getLogger("practice_forge.llm")
    llm_logger.setLevel(logging.INFO)
    llm_logger.propagate = False

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(logging.Formatter("%(message)s"))
    llm_logger.addHandler(stream_handler)

    _LLM_USAGE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(_LLM_USAGE_LOG_PATH, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(message)s"))
    llm_logger.addHandler(file_handler)


_configure_logging()


@profiles_app.command("list")
def profiles_list() -> None:
    """List every configured discipline profile."""
    for profile in list_profiles():
        typer.echo(f"{profile.key:20s} {profile.display_name}")


@profiles_app.command("show")
def profiles_show(key: str) -> None:
    """Show one discipline profile's full config."""
    profile = load_profile(key)
    typer.echo(profile.model_dump_json(indent=2))


@profiles_app.command("sync")
def profiles_sync() -> None:
    """Upsert profiles/*.yaml into the disciplines and topic_nodes tables."""
    with session_scope() as session:
        synced = sync_disciplines(session)
        sync_topic_nodes(session)
    for profile in synced:
        typer.echo(f"synced {profile.key}")


@app.command()
def ingest(
    pdf_path: Path,
    discipline: str = typer.Option(..., "--discipline", help="Discipline profile key."),
    uploaded_by: str = typer.Option(
        None, "--uploaded-by", help="Defaults to the current OS user."
    ),
) -> None:
    """Ingest a textbook PDF: exact-hash dedup, cross-edition MinHash dedup,
    per-page extraction (S1)."""
    if not pdf_path.exists():
        typer.echo(f"No such file: {pdf_path}", err=True)
        raise typer.Exit(code=1)

    with session_scope() as session:
        result = run_ingest(
            session,
            pdf_path,
            discipline_key=discipline,
            uploaded_by=uploaded_by or getpass.getuser(),
        )

    if result.dedup_hit:
        typer.echo(f"dedup hit ({result.dedup_hit}) - reusing book_id={result.book_id}")
    else:
        typer.echo(f"ingested book_id={result.book_id}, {result.pages_ingested} pages")


@app.command()
def structure(book_id: str) -> None:
    """Detect chapter/section boundaries (TOC-driven, regex fallback) and
    map them onto topic nodes (S2)."""
    with session_scope() as session:
        sections, report = run_structure(session, uuid.UUID(book_id))
    typer.echo(
        f"method={report.method} toc_entries_parsed={report.toc_entries_parsed} "
        f"chapters_located={report.chapters_located}"
    )
    for section in sections:
        typer.echo(f"pages {section.page_start}-{section.page_end}: {section.title}")


@app.command()
def detect(book_id: str) -> None:
    """Detect worked examples/exercises via regex candidates + a batched LLM
    confirm pass, persisted as SourceProblem rows (S3). Requires structure
    (S2) to have run first and GEMINI_API_KEY to be set (see
    config/llm_routing.yaml for the stage->provider/model mapping)."""
    confirm_fn = make_default_batch_confirm_fn(job_id=f"detect-{book_id}")
    with session_scope() as session:
        problems = run_detection_(session, uuid.UUID(book_id), confirm_fn=confirm_fn)
    for problem in problems:
        typer.echo(f"page {problem.page_no}: {problem.kind.value}")
    typer.echo(f"{len(problems)} problems detected")


@app.command()
def figures(book_id: str) -> None:
    """S4, descoped for v1 (see docs/adr/0007): classifies figure_dependency
    from problem text alone and excludes ESSENTIAL problems
    (is_solvable=False). No figure interpretation — detect and exclude
    only."""
    with session_scope() as session:
        counts = run_figure_descope(session, uuid.UUID(book_id))
    typer.echo(f"figure_dependency=none: {counts['none']}")
    typer.echo(f"figure_dependency=essential (excluded): {counts['essential_excluded']}")


@app.command()
def generate(
    book: str = typer.Option(..., "--book", help="Book ID to select and generate from."),
    limit: int = typer.Option(
        20, "--limit", help="Generate variants+solutions for at most this many selected problems."
    ),
) -> None:
    """S7 selection -> S8 (variant generation) -> S9 Part A (core solver +
    real sandbox execution verification). Every verified_answer comes from
    actually running generated code in the sandbox, never from anything
    the LLM merely claims. Rendering/ledger-commit (S9 Part B, S10) not
    implemented yet — see PROGRESS.md."""
    book_id = uuid.UUID(book)
    with session_scope() as session:
        book_row = session.get(BookORM, book_id)
        assert book_row is not None
        discipline = session.get(DisciplineORM, book_row.discipline_id)
        assert discipline is not None
        profile = load_profile(discipline.key)
        # Real per-discipline image (has CoolProp etc. — see
        # docker/sandbox/mechanical.Dockerfile), not the shared base:
        # found live that a real generated solution needed CoolProp for
        # steam properties and failed with ModuleNotFoundError until this
        # image existed and was actually used instead of DEFAULT_IMAGE.
        sandbox_image = discipline.sandbox_image_tag
        extra_libs = [lib for lib in profile.solver_libs if lib not in ("pint", "numpy", "sympy", "scipy", "matplotlib")]

        selection_result = run_selection(session, book_id)
        if not selection_result.can_reach_target:
            typer.echo(f"cannot reach target: {selection_result.reason}", err=True)
            raise typer.Exit(code=1)

        attachments = select_extension_attachments(selection_result.selected)
        # One shared client for both stages, not one each: the RPM token
        # bucket is in-memory per RateLimiter instance (see
        # llm/rate_limiter.py) — two separate LLMClient()s routed to the
        # same real model each start with a full bucket, so their combined
        # burst can exceed the real per-model RPM cap even though a
        # limiter exists. Found live: a real 429 fired mid-run today with
        # two separate clients both on gemini-flash-lite-latest.
        client = LLMClient()

        verified = 0
        failed = 0
        skipped = 0
        for i, member in enumerate(selection_result.selected[:limit]):
            existing = session.execute(
                sa_select(VariantORM).where(
                    VariantORM.concept_cluster_id == member.cluster_id,
                    VariantORM.verification_status == VerificationStatus.VERIFIED,
                )
            ).first()
            if existing is not None:
                typer.echo(f"  [{i}] {member.card.name[:50]:50s} -> already verified, skipping")
                skipped += 1
                continue

            problem = session.get(SourceProblemORM, member.card.source_problem_id)
            assert problem is not None

            variant = generate_variant(
                client,
                f"s8-{book_id}-{i}",
                member.cluster_id,
                member.card,
                problem,
                member.difficulty_tier,
            )
            if variant is None:
                typer.echo(f"  [{i}] {member.card.name[:50]:50s} -> variant generation failed to parse")
                failed += 1
                continue

            extension = attachments.get(member.card.id)
            if extension is not None:
                variant.extension_type = extension

            generate_and_verify_solution(
                client,
                f"s9-{book_id}-{i}",
                member.card,
                variant,
                extra_libs=extra_libs,
                sandbox_image=sandbox_image,
                sandbox_timeout_s=15,
            )
            session.add(variant)
            session.commit()

            status = variant.verification_status.value
            typer.echo(f"  [{i}] {member.card.name[:50]:50s} -> {status}")
            if status == "verified":
                verified += 1
            else:
                failed += 1

    typer.echo(f"generated: {verified + failed}, verified: {verified}, failed: {failed}, skipped: {skipped}")


@app.command()
def calibrate(
    book: str = typer.Option(..., "--book", help="Book ID to calibrate against."),
    limit: int = typer.Option(
        30, "--limit", help="Max SourceProblems (with a parseable final_answer) to solve."
    ),
) -> None:
    """Calibration mode: solves real SourceProblems with UNCHANGED source
    parameters (no S8 rewrite) and compares against the book's own printed
    final_answer, within 1% relative tolerance. The strongest accuracy
    check available — a mismatch here is attributable to the solver, not
    to a rewritten problem. Nothing is persisted."""
    book_id = uuid.UUID(book)
    with session_scope() as session:
        book_row = session.get(BookORM, book_id)
        assert book_row is not None
        discipline = session.get(DisciplineORM, book_row.discipline_id)
        assert discipline is not None
        profile = load_profile(discipline.key)
        sandbox_image = discipline.sandbox_image_tag
        extra_libs = [lib for lib in profile.solver_libs if lib not in ("pint", "numpy", "sympy", "scipy", "matplotlib")]

        client = LLMClient()
        report = run_calibration(
            session,
            book_id,
            client,
            limit=limit,
            sandbox_image=sandbox_image,
            extra_libs=extra_libs,
        )

    for row in report.rows:
        typer.echo(f"  page {row.page_no:4d} [{row.outcome:24s}] {row.detail[:160]}")

    typer.echo("")
    typer.echo(f"candidates considered: {report.total_candidates}")
    typer.echo(f"  matched:                   {report.matched}")
    typer.echo(f"  mismatched:                {report.mismatched}")
    typer.echo(f"  unparseable book answer:   {report.unparseable_book_answer}")
    typer.echo(f"  solver failed to verify:   {report.solver_failed}")
    denom = report.matched + report.mismatched
    if denom:
        typer.echo(f"accuracy over comparable rows: {report.matched}/{denom} ({100 * report.matched / denom:.1f}%)")


@app.command()
def render(
    book: str = typer.Option(..., "--book", help="Book ID to render a problem set for."),
    out: str = typer.Option("data/generated", "--out", help="Output directory."),
    title: str = typer.Option("Practice Problem Set", "--title"),
) -> None:
    """S10: renders the real, already-verified selected set (S7 + S8/S9)
    into a student handout PDF, a faculty solutions manual PDF (with
    execution-verified answers), and a code/ folder of the real generated
    Python for each problem. No LLM call. Ledger-commit (writing an
    IssuedLedger row) is not done here — see PROGRESS.md."""
    book_id = uuid.UUID(book)
    out_dir = Path(out) / book
    with session_scope() as session:
        result = run_render(session, book_id, out_dir, title)
    typer.echo(f"problems rendered: {result.problem_count}")
    typer.echo(f"student handout: {result.student_pdf_path}")
    typer.echo(f"solutions manual: {result.solutions_pdf_path}")
    typer.echo(f"code folder: {result.code_dir}")


@app.command()
def distill(book_id: str) -> None:
    """S5: concept distillation, fingerprinting, and clustering over every
    is_solvable SourceProblem for this book. Real batched Gemini call."""
    with session_scope() as session:
        result = run_concept_distillation(session, uuid.UUID(book_id), job_id=f"distill-{book_id}")
    typer.echo(f"distilled: {result['distilled']}")
    typer.echo(f"LaTeX parse failures: {result['parse_failures']}")
    typer.echo(f"clusters: {result['clusters']}")


@app.command()
def score(book_id: str) -> None:
    """S6: six-axis candidate scoring (real batched Gemini call) +
    deterministic eligible_extension_types gating."""
    with session_scope() as session:
        result = run_scoring(session, uuid.UUID(book_id), job_id=f"score-{book_id}")
    typer.echo(f"scored: {result.get('scored', 0)} / {result.get('candidates', 0)} candidates")


@app.command()
def select(book_id: str) -> None:
    """S7: constrained selection over the real scored pool for this book.
    No LLM call. Reports honestly if the pool can't reach the 20-problem
    target rather than silently returning fewer."""
    with session_scope() as session:
        result = run_selection(session, uuid.UUID(book_id))
    typer.echo(f"pool size: {result.pool_size}")
    typer.echo(f"can reach 20-problem target: {result.can_reach_target}")
    typer.echo(f"reason: {result.reason}")
    for constraint, satisfied in result.constraints_satisfied.items():
        typer.echo(f"  [{'PASS' if satisfied else 'FAIL'}] {constraint}")
    for relaxation in result.relaxations_applied:
        typer.echo(f"  [RELAXED] {relaxation}")


if __name__ == "__main__":
    app()
