"""`pf` — the practice-forge CLI.

`generate` is a stub until S6-S10 land (Phases P6-P10); `profiles` and
`ingest` are fully functional.
"""

from __future__ import annotations

import getpass
from pathlib import Path

import typer

from practice_forge.db.base import session_scope
from practice_forge.ingest.pipeline import run_ingest
from practice_forge.profiles.loader import list_profiles, load_profile
from practice_forge.profiles.sync import sync_disciplines

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
    """Upsert profiles/*.yaml into the disciplines table."""
    with session_scope() as session:
        synced = sync_disciplines(session)
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


if __name__ == "__main__":
    app()
