"""CLI: generate (single or from JSON) and eval (10 prompts)."""

import json
import os
from pathlib import Path

import typer
from dotenv import load_dotenv

# Load .env so OPENAI_API_KEY is set
load_dotenv()

app = typer.Typer(help="Syllabus V0: generate course from intake (CLI only)")


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
):
    """Run pipeline for each of the 10 V0 test prompts and write outputs to out_dir."""
    if not os.environ.get("OPENAI_API_KEY"):
        typer.echo("Error: OPENAI_API_KEY not set.", err=True)
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


@app.command()
def index_rag(
    path: str = typer.Argument(..., help="Directory path containing .txt/.md files to index"),
):
    """Index documents from a directory into the RAG vector store (for research retrieval)."""
    if not os.environ.get("OPENAI_API_KEY"):
        typer.echo("Error: OPENAI_API_KEY not set.", err=True)
        raise typer.Exit(1)
    from syllabus.rag.index import index_directory

    n = index_directory(path)
    typer.echo(f"Indexed {n} chunks from {path}.")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
