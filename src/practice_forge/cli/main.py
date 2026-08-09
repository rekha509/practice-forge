"""`pf` — the practice-forge CLI.

`ingest` and `generate` are stubs until their pipeline stages land (P2 and
P7-P10 respectively); `profiles` is fully functional now since it only
exercises the declarative discipline config (see profiles/loader.py).
"""

from __future__ import annotations

from pathlib import Path

import typer

from practice_forge.profiles.loader import list_profiles, load_profile

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


@app.command()
def ingest(pdf_path: Path, discipline: str | None = None) -> None:
    """Ingest a textbook PDF (S1: file/book dedup, page extraction).

    Not yet implemented — lands in Phase P2. See PROGRESS.md.
    """
    typer.echo(
        "pf ingest is not implemented yet (Phase P2 — see PROGRESS.md 'Next Immediate Task').",
        err=True,
    )
    raise typer.Exit(code=1)


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
