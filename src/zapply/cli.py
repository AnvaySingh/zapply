"""zapply command-line interface.

Phase 0 ships two commands:

* ``hello``       — a zero-dependency sanity check (no API call, no keys).
* ``trace-test``  — makes exactly one real, traced LLM call, proving the seam and the
                    telescope both work.
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from . import __version__
from .config import get_settings
from .llm import LLMClient, LLMError

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="zapply — a local job-application copilot (Employable's brain without its hands).",
)
console = Console()


@app.command()
def hello(name: str = typer.Option("world", help="Who to greet.")) -> None:
    """Print a greeting. No API call — just proves the CLI wiring is live."""
    console.print(f"[bold green]Hello, {name}![/] zapply v{__version__} is wired up.")


@app.command("trace-test")
def trace_test(
    prompt: str = typer.Option(
        "In one short sentence, greet me and name which AI model you are.",
        help="The prompt to send.",
    ),
) -> None:
    """Make one traced LLM call. Phase 0's definition of done.

    With Langfuse keys set, this call appears as a trace in your Langfuse dashboard.
    Without them, the call still runs — tracing is simply a no-op.
    """
    settings = get_settings()

    try:
        client = LLMClient(settings)
    except LLMError as exc:
        console.print(f"[bold red]Configuration error:[/] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"[dim]Provider → {client.provider_name} ({client.model})[/]")
    if settings.tracing_enabled:
        console.print(f"[dim]Tracing → {settings.langfuse_host}[/]")
    else:
        console.print(
            "[yellow]Tracing disabled[/] (no Langfuse keys). The call will still run; "
            "set LANGFUSE_* in .env to see it in the dashboard."
        )

    try:
        with console.status("[cyan]Calling the model…[/]"):
            # Headroom matters: "thinking" models (e.g. Gemini 3.x) spend part of the token
            # budget on hidden reasoning, so too small a cap can truncate the visible answer.
            reply = client.complete(prompt, max_tokens=1024)
    except LLMError as exc:
        console.print(f"[bold red]LLM call failed:[/] {exc}")
        raise typer.Exit(code=1) from exc
    finally:
        client.flush()

    console.print(Panel(reply, title=f"[bold]{client.provider_name} · {client.model}[/]", border_style="green"))

    if settings.tracing_enabled:
        console.print(
            "[green]✓ Traced.[/] Open your Langfuse project to see this call as a trace."
        )


def _postings_table(postings: list, title: str) -> Table:
    table = Table(title=title, show_lines=False, expand=True)
    table.add_column("Company", style="cyan", no_wrap=True)
    table.add_column("Title", style="bold")
    table.add_column("Location")
    table.add_column("Source", style="dim")
    for p in postings:
        table.add_row(p.company, p.title, p.location or "—", p.source)
    return table


@app.command()
def ingest(
    config: Path = typer.Option(Path("companies.yaml"), help="Path to companies.yaml."),
    state: Path = typer.Option(
        Path(".ingest_state.json"), help="Where to persist 'already seen' keys."
    ),
    show_all: bool = typer.Option(
        False, "--all", help="Show every unique posting, not just new ones."
    ),
    limit: int = typer.Option(25, help="Max postings to display."),
    no_persist: bool = typer.Option(
        False, "--no-persist", help="Don't update the seen-store (dry run)."
    ),
) -> None:
    """Poll all configured read-only sources → normalise → dedup → show new postings."""
    from .ingest import IngestService, SeenStore, load_sources

    if not config.exists():
        console.print(f"[bold red]No config at[/] {config}. See companies.yaml.")
        raise typer.Exit(code=1)

    sources = load_sources(config)
    if not sources:
        console.print("[yellow]No usable sources in config.[/]")
        raise typer.Exit(code=1)

    store = SeenStore(state)
    service = IngestService(sources, store)
    with console.status(f"[cyan]Polling {len(sources)} source(s)…[/]"):
        result = service.run(persist=not no_persist)

    console.print(
        f"[dim]Fetched[/] {result.fetched}  →  "
        f"[dim]unique[/] {result.unique}  →  "
        f"[bold green]new[/] {len(result.new)}"
        + ("  [dim](dry run — state not saved)[/]" if no_persist else "")
    )

    to_show = result.postings if show_all else result.new
    label = "All unique postings" if show_all else "New postings this run"
    if not to_show:
        console.print(f"[green]No {'' if show_all else 'new '}postings to show.[/]")
        return
    console.print(_postings_table(to_show[:limit], f"{label} (showing {min(len(to_show), limit)})"))


@app.command("ingest-file")
def ingest_file(
    path: Path = typer.Argument(..., help="Path to a text/markdown/HTML job description."),
    company: str = typer.Option(..., help="Company for this posting."),
    title: str = typer.Option(..., help="Role title for this posting."),
    location: str = typer.Option(None, help="Optional location."),
) -> None:
    """Ingest a single pasted/downloaded JD file through the same pipeline."""
    from .ingest import PasteSource

    if not path.exists():
        console.print(f"[bold red]No file at[/] {path}")
        raise typer.Exit(code=1)

    source = PasteSource.from_file(path, company=company, title=title, location=location)
    postings = source.fetch()
    console.print(_postings_table(postings, "Ingested from file"))
    if postings:
        preview = postings[0].description[:400]
        console.print(Panel(preview or "[dim](no description)[/]", title="Description preview"))


@app.command("extract-resume")
def extract_resume(
    path: Path = typer.Argument(..., help="Path to a resume (text/markdown)."),
    backend: str = typer.Option("native", help="Extraction backend: native | instructor."),
) -> None:
    """Resume file → structured Profile (via the chosen extraction backend)."""
    from .extract import extract_profile

    if not path.exists():
        console.print(f"[bold red]No file at[/] {path}")
        raise typer.Exit(code=1)

    with console.status(f"[cyan]Extracting profile ({backend})…[/]"):
        profile = extract_profile(path.read_text(encoding="utf-8"), backend=backend)

    console.print(Panel(profile.model_dump_json(indent=2), title=f"Profile · {backend}", border_style="green"))


@app.command("extract-jd")
def extract_jd(
    path: Path = typer.Argument(..., help="Path to a job description (text/markdown)."),
    backend: str = typer.Option("native", help="Extraction backend: native | instructor."),
) -> None:
    """Job-description file → structured Requirements (via the chosen extraction backend)."""
    from .extract import extract_requirements

    if not path.exists():
        console.print(f"[bold red]No file at[/] {path}")
        raise typer.Exit(code=1)

    with console.status(f"[cyan]Extracting requirements ({backend})…[/]"):
        reqs = extract_requirements(path.read_text(encoding="utf-8"), backend=backend)

    console.print(Panel(reqs.model_dump_json(indent=2), title=f"Requirements · {backend}", border_style="green"))


@app.command()
def match(
    resume: Path = typer.Option(..., help="Path to a resume file."),
    jd: Path = typer.Option(..., help="Path to a job-description file."),
    backend: str = typer.Option("native", help="Extraction backend: native | instructor."),
) -> None:
    """Score a resume against a job description: extract both, then embed + compare."""
    from .extract import extract_profile, extract_requirements
    from .match import Matcher

    for label, p in (("resume", resume), ("jd", jd)):
        if not p.exists():
            console.print(f"[bold red]No {label} file at[/] {p}")
            raise typer.Exit(code=1)

    with console.status("[cyan]Extracting profile & requirements…[/]"):
        profile = extract_profile(resume.read_text(encoding="utf-8"), backend=backend)
        reqs = extract_requirements(jd.read_text(encoding="utf-8"), backend=backend)
    with console.status("[cyan]Embedding & scoring…[/]"):
        result = Matcher().score(profile, reqs)

    colour = "green" if result.score >= 65 else "yellow" if result.score >= 45 else "red"
    console.print(
        Panel(
            f"[bold {colour}]{result.score}/100[/]  (cosine {result.similarity:.3f})\n\n"
            f"{result.rationale}",
            title=f"Match · {profile.name or 'candidate'} → {reqs.title}",
            border_style=colour,
        )
    )


@app.command()
def draft(
    resume: Path = typer.Option(..., help="Path to a resume file."),
    jd: Path = typer.Option(..., help="Path to a job-description file."),
    backend: str = typer.Option("native", help="Extraction backend: native | instructor."),
) -> None:
    """Draft grounded tailored bullets + screening answers, then run the faithfulness gate."""
    from .draft import check_draft
    from .draft import draft as draft_packet
    from .extract import extract_profile, extract_requirements

    for label, p in (("resume", resume), ("jd", jd)):
        if not p.exists():
            console.print(f"[bold red]No {label} file at[/] {p}")
            raise typer.Exit(code=1)

    with console.status("[cyan]Extracting…[/]"):
        profile = extract_profile(resume.read_text(encoding="utf-8"), backend=backend)
        reqs = extract_requirements(jd.read_text(encoding="utf-8"), backend=backend)
    with console.status("[cyan]Drafting (grounded)…[/]"):
        packet = draft_packet(profile, reqs)

    report = check_draft(packet, profile, reqs)

    bullets = "\n".join(f"• {b.text}" for b in packet.bullets) or "[dim](none)[/]"
    console.print(Panel(bullets, title="Tailored bullets", border_style="cyan"))
    for a in packet.answers:
        console.print(Panel(a.answer, title=a.question, border_style="cyan"))

    if report.is_faithful:
        console.print("[bold green]✓ Faithfulness gate passed[/] — no fabricated skills or employers.")
    else:
        console.print(f"[bold red]✗ Faithfulness gate FAILED[/] ({len(report.violations)} violation(s)):")
        for v in report.violations:
            console.print(f"  [red]-[/] {v.where}: {v.kind} — {v.detail}")


@app.command()
def apply(
    resume: Path = typer.Option(..., help="Path to your resume file."),
    config: Path = typer.Option(Path("companies.yaml"), help="Sources to ingest from."),
    top_k: int = typer.Option(3, help="How many top-ranked postings get drafted (LLM cost)."),
    backend: str = typer.Option("native", help="Extraction backend: native | instructor."),
    out: Path = typer.Option(Path("packets"), help="Directory to write approved packets."),
    yes: bool = typer.Option(False, "--yes", help="Auto-approve faithful drafts (non-interactive)."),
) -> None:
    """End-to-end: ingest → prefilter → extract → match → draft → REVIEW → packet."""
    from .extract import extract_profile
    from .ingest import deduplicate, load_sources
    from .orchestrate import ApplicationStatus, PipelineConfig, approve, default_pipeline, reject
    from .packet import build_packet

    if not resume.exists():
        console.print(f"[bold red]No resume at[/] {resume}")
        raise typer.Exit(code=1)

    # 1) Profile (1 LLM call).
    with console.status("[cyan]Extracting your profile…[/]"):
        profile = extract_profile(resume.read_text(encoding="utf-8"), backend=backend)

    # 2) Ingest postings (network, no LLM).
    with console.status("[cyan]Ingesting postings…[/]"):
        postings = []
        for source in load_sources(config):
            try:
                postings.extend(source.fetch())
            except Exception:  # noqa: BLE001 - one flaky board shouldn't stop the run
                pass
        postings = deduplicate(postings)

    if not postings:
        console.print("[yellow]No postings ingested.[/]")
        raise typer.Exit(code=1)

    # 3) Pipeline: local prefilter over ALL, LLM extract+draft on top-K only.
    console.print(f"[dim]Ingested {len(postings)} postings; drafting the top {top_k}…[/]")
    with console.status("[cyan]Prefilter → extract → match → draft…[/]"):
        apps = default_pipeline(backend=backend).run(
            profile, postings, PipelineConfig(top_k=top_k)
        )

    # 4) Show the shortlist.
    table = Table(title="Shortlist", expand=True)
    table.add_column("#", style="dim")
    table.add_column("Role")
    table.add_column("Match", justify="right")
    table.add_column("Faithful", justify="center")
    for i, a in enumerate(apps):
        ok = "[green]✓[/]" if a.is_faithful else "[red]✗ blocked[/]"
        table.add_row(str(i + 1), a.label, f"{a.match.score}", ok)
    console.print(table)

    # 5) Review gate (the human, enforced as a program).
    out.mkdir(parents=True, exist_ok=True)
    written = 0
    for a in apps:
        if a.status == ApplicationStatus.blocked:
            console.print(f"[red]⨯ {a.label}[/] blocked by faithfulness gate — not offered for approval.")
            continue

        console.print(Panel("\n".join(f"• {b.text}" for b in a.draft.bullets), title=f"Draft · {a.label}"))
        decision = True if yes else typer.confirm(f"Approve packet for '{a.label}'?", default=False)
        if not decision:
            reject(a)
            console.print(f"[yellow]— skipped {a.label}[/]")
            continue

        approve(a)  # raises if not faithful (defence in depth)
        packet_md = build_packet(a)
        dest = out / f"{a.posting.source}_{a.posting.source_id}.md".replace("/", "_")
        dest.write_text(packet_md, encoding="utf-8")
        written += 1
        console.print(f"[green]✓ wrote[/] {dest}")

    console.print(f"\n[bold green]Done.[/] {written} packet(s) written to {out}/.")


@app.command()
def version() -> None:
    """Print the version."""
    console.print(f"zapply v{__version__}")


if __name__ == "__main__":  # pragma: no cover
    app()
