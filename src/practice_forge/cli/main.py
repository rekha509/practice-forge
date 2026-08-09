"""`pf` — the practice-forge CLI.

`generate` is a stub until S6-S10 land (Phases P6-P10); `profiles` and
`ingest` are fully functional.
"""

from __future__ import annotations

import getpass
import uuid
from pathlib import Path

import typer

from practice_forge.concepts.concepts import run_concept_distillation
from practice_forge.db.base import session_scope
from practice_forge.detection.detection import make_default_batch_confirm_fn
from practice_forge.detection.detection import run_detection as run_detection_
from practice_forge.figures.figures import run_figure_descope
from practice_forge.ingest.pipeline import run_ingest
from practice_forge.profiles.loader import list_profiles, load_profile
from practice_forge.profiles.sync import sync_disciplines, sync_topic_nodes
from practice_forge.scoring.scoring import run_scoring
from practice_forge.selection.selection import run_selection
from practice_forge.structure.structure import run_structure

app = typer.Typer(name="pf", help="Generate execution-verified engineering practice problem sets.")
profiles_app = typer.Typer(help="Inspect discipline profiles.")
app.add_typer(profiles_app, name="profiles")


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
    """Detect chapter/section boundaries and map them onto topic nodes (S2)."""
    with session_scope() as session:
        sections = run_structure(session, uuid.UUID(book_id))
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
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Run selection + solve + render (S6-S10) for a book/course.

    Not yet implemented — lands across Phases P6-P10. See PROGRESS.md.
    """
    typer.echo(
        "pf generate is not implemented yet (Phases P6-P10 — see PROGRESS.md 'Next Immediate Task').",
        err=True,
    )
    raise typer.Exit(code=1)


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


if __name__ == "__main__":
    app()
