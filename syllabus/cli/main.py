"""CLI: generate (single or from JSON) and eval (10 prompts)."""

import json
import os
from pathlib import Path

import typer
from dotenv import load_dotenv

# Load .env so OPENAI_API_KEY is set (try project root then cwd)
_project_root = Path(__file__).resolve().parent.parent.parent
load_dotenv(_project_root / ".env")
load_dotenv()

_ERR_OPENAI_KEY = "Error: OPENAI_API_KEY not set."

_DIM_NAMES = {
    "1": "medical_accuracy",
    "2": "structural_coherence",
    "3": "tone",
    "4": "compliance",
    "5": "completeness",
    "6": "objective_coherence",
    "7": "scaffolding_quality",
    "8": "knowledge_topology_fit",
    "9": "emotional_calibration",
}

app = typer.Typer(help="Syllabus V0: generate course from intake (CLI only)")


def _display_rubric_summary(summary: dict) -> None:
    """Print rubric scorecard summary to stdout."""
    typer.echo(
        f"Scored {summary.get('total', 0)} courses. "
        f"Passed (no automated fails): {summary.get('passed_automated_plus_hr', 0)}"
    )
    for d in sorted(summary.get("by_dimension", {}).keys(), key=int):
        by_d = summary["by_dimension"][d]
        typer.echo(
            f"  Dim {d}: pass={by_d.get('pass_count', 0)} "
            f"fail={by_d.get('fail_count', 0)} "
            f"human_review={by_d.get('human_review_count', 0)}"
        )


def _write_rubric_report(summary: dict, report: str | None, markdown: str | None) -> None:
    """Optionally write rubric results to JSON and/or markdown files."""
    if report:
        Path(report).parent.mkdir(parents=True, exist_ok=True)
        with open(report, "w") as f:
            json.dump(summary, f, indent=2)
        typer.echo(f"Report written to {report}")
    if markdown:
        Path(markdown).parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "# Layer 1 Eval — 9-Dimension Rubric Scorecard",
            "",
            f"Total courses: {summary.get('total', 0)}",
            f"Passed (automated + human-review): {summary.get('passed_automated_plus_hr', 0)}",
            "",
            "## By dimension",
            "",
            "| Dim | Name | Pass | Fail | Human review |",
            "|-----|------|------|------|--------------|",
        ]
        for d in sorted(summary.get("by_dimension", {}).keys(), key=int):
            by_d = summary["by_dimension"][d]
            name = _DIM_NAMES.get(d, "?")
            lines.append(
                f"| {d} | {name} | {by_d.get('pass_count', 0)} | {by_d.get('fail_count', 0)} | {by_d.get('human_review_count', 0)} |"
            )
        with open(markdown, "w") as f:
            f.write("\n".join(lines))
        typer.echo(f"Markdown written to {markdown}")


def _run_and_output(intake: str | dict, output_path: str | None) -> dict | None:
    """Run pipeline and return course_spec dict or None; optionally write JSON."""
    from syllabus.pipeline import run_pipeline

    spec = run_pipeline(intake)
    if spec is None:
        return None
    data = spec.model_dump(mode="json")
    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(data, f, indent=2)
    return data


@app.command()
def generate(
    prompt: str = typer.Option(None, "--prompt", "-p", help="Free-text intake (patient message)"),
    intake: str = typer.Option(None, "--intake", "-i", help="Path to intake JSON file"),
    out: str = typer.Option(None, "--out", "-o", help="Write CourseSpec JSON to this path"),
):
    """Generate a course from a single prompt or intake JSON."""
    if not os.environ.get("OPENAI_API_KEY"):
        typer.echo("Error: OPENAI_API_KEY not set. Set it in .env or environment.", err=True)
        raise typer.Exit(1)
    raw: str | dict
    if intake:
        p = Path(intake)
        if not p.exists():
            typer.echo(f"Error: file not found: {intake}", err=True)
            raise typer.Exit(1)
        with open(p) as f:
            raw = json.load(f)
    elif prompt is not None:
        raw = prompt
    else:
        typer.echo("Provide either --prompt or --intake.", err=True)
        raise typer.Exit(1)
    typer.echo("Running pipeline...")
    data = _run_and_output(raw, out)
    if data is None:
        typer.echo("Pipeline failed (see errors above).", err=True)
        raise typer.Exit(1)
    if not out:
        typer.echo(json.dumps(data, indent=2))
    else:
        typer.echo(f"Wrote CourseSpec to {out}")


@app.command()
def eval(
    prompts: str = typer.Option(
        None,
        "--prompts",
        "-P",
        help="Path to JSON file with list of prompt strings (default: built-in 10 V0 prompts)",
    ),
    out_dir: str = typer.Option(
        "out",
        "--out-dir",
        "-o",
        help="Directory to write one CourseSpec JSON per prompt",
    ),
    rubric: bool = typer.Option(
        False,
        "--rubric",
        "-r",
        help="After eval, score courses on the 9-dimension rubric and show results",
    ),
    report: str = typer.Option(
        None,
        "--report",
        help="With --rubric: write scorecard JSON to this path",
    ),
    markdown: str = typer.Option(
        None,
        "--markdown",
        help="With --rubric: write scorecard markdown to this path",
    ),
):
    """Run pipeline for each of the 10 V0 test prompts and write outputs to out_dir. No time limit."""
    if not os.environ.get("OPENAI_API_KEY"):
        typer.echo(_ERR_OPENAI_KEY, err=True)
        raise typer.Exit(1)
    if prompts:
        with open(prompts) as f:
            prompt_list = json.load(f)
    else:
        # Built-in 10 prompts (PRD Section 8.3)
        prompt_list = [
            "I was just diagnosed with PCOS and I'm starting IUI next month",
            "My AMH is 0.8 and my doctor said I should consider IVF",
            "We're about to start our first IVF cycle and I'm terrified",
            "Our third transfer just failed and I don't know what to do",
            "I'm 32 and thinking about freezing my eggs",
            "My wife is going through IVF and I want to understand it better",
            "I have unexplained infertility and have been trying for 2 years",
            "I don't have a diagnosis yet but we've been trying for a year",
            "What is PGT-A testing and should I ask about it?",
            "I just had my egg retrieval and got 4 eggs. Is that normal?",
        ]
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    success = 0
    for i, p in enumerate(prompt_list):
        typer.echo(f"[{i + 1}/{len(prompt_list)}] {p[:50]}...")
        out_file = out_path / f"course_{i + 1:02d}.json"
        data = _run_and_output(p, str(out_file))
        if data is not None:
            success += 1
    typer.echo(f"Done: {success}/{len(prompt_list)} courses written to {out_dir}/")
    if rubric:
        from syllabus.eval.rubric import score_directory

        result = score_directory(out_dir)
        if result.get("error"):
            typer.echo(result["error"], err=True)
            raise typer.Exit(1)
        typer.echo("")
        typer.echo("--- 9-dimension rubric ---")
        _display_rubric_summary(result.get("summary", {}))
        _write_rubric_report(result, report, markdown)


@app.command("eval-rubric")
def eval_rubric(
    out_dir: str = typer.Option(
        "out",
        "--out-dir",
        "-o",
        help="Directory containing course_01.json … course_10.json to score",
    ),
    report: str = typer.Option(
        None,
        "--report",
        "-r",
        help="Write scorecard JSON to this path",
    ),
    markdown: str = typer.Option(
        None,
        "--markdown",
        "-m",
        help="Write scorecard markdown to this path",
    ),
):
    """Score course JSONs on the 9-dimension rubric (PRD Addendum E.1, E.3). Run after 'eval' to get before/after scores."""
    from syllabus.eval.rubric import score_directory

    result = score_directory(out_dir)
    if result.get("error"):
        typer.echo(result["error"], err=True)
        raise typer.Exit(1)
    _display_rubric_summary(result.get("summary", {}))
    _write_rubric_report(result, report, markdown)


@app.command()
def index_rag(
    path: str = typer.Argument(..., help="Directory path containing .txt/.md files to index"),
):
    """Index documents from a directory into the RAG vector store (for research retrieval)."""
    if not os.environ.get("OPENAI_API_KEY"):
        typer.echo(_ERR_OPENAI_KEY, err=True)
        raise typer.Exit(1)
    from syllabus.rag.index import index_directory

    n = index_directory(path)
    typer.echo(f"Indexed {n} chunks from {path}.")


@app.command("index-pubmed")
def index_pubmed_cmd(
    max_per_query: int = typer.Option(
        None, "--max-per-query", "-n", help="Max abstracts per query (default: 50 for V1 ~500 docs)"
    ),
    query: list[str] = typer.Option(
        None,
        "--query",
        "-q",
        help="PubMed search query (repeat for multiple); default: fertility set",
    ),
):
    """Index PubMed abstracts into the RAG vector store (PRD T-012). Uses default fertility queries if none given."""
    if not os.environ.get("OPENAI_API_KEY"):
        typer.echo(_ERR_OPENAI_KEY, err=True)
        raise typer.Exit(1)
    from syllabus.rag.pubmed import DEFAULT_MAX_PER_QUERY, index_pubmed

    queries = query if query else None
    n = index_pubmed(
        queries=queries,
        max_per_query=max_per_query if max_per_query is not None else DEFAULT_MAX_PER_QUERY,
    )
    typer.echo(f"Indexed {n} chunks from PubMed.")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
