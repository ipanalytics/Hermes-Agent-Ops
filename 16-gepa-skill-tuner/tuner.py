#!/usr/bin/env python3
"""gepa-skill-tuner — optimize a Hermes prompt or skill against a measurable task set.

GEPA (Genetic-Pareto, arXiv 2507.19457) improves *text* parameters by having an LLM read
full execution traces and reflect in natural language, instead of collapsing a rollout into
one scalar reward. That makes it the right tool for the parameter an agent actually ships:
its system prompt, a cron prompt, or a SKILL.md.

This wrapper keeps the harness honest:
  * the dataset is a file (JSONL of {"input", "answer"}), not a vibe,
  * **repeated examples are collapsed before the split** — duplicates both inflate the
    validation score (the same row leaks into train *and* val) and, on mixture-of-experts
    optimizers, drive the reflector into memorising the repeat instead of the rule,
  * the metric is exact-match or your own evaluator module,
  * the run is capped by --max-metric-calls, so the cost is bounded before you start,
  * the output is a JSON report plus a unified diff against the seed prompt, so the result
    can be reviewed (and reverted) like any other change.

Usage:
  tuner.py --prompt-file seed_prompt.txt --dataset tasks.jsonl --out report.json
  tuner.py --skill ~/.hermes/skills/foo/SKILL.md --dataset tasks.jsonl --section "## Rules"
  tuner.py --prompt-file p.txt --dataset tasks.jsonl --evaluator my_metric.py

Exit codes: 0 run completed, 2 setup/API error.
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import sys
import time
from pathlib import Path

DEFAULT_TASK_LM = os.environ.get("GEPA_TASK_LM", "openrouter/deepseek/deepseek-chat")
DEFAULT_REFLECTION_LM = os.environ.get("GEPA_REFLECTION_LM", "openrouter/deepseek/deepseek-chat")


def load_dataset(path: str) -> list[dict]:
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        item = json.loads(line)
        if "input" not in item or "answer" not in item:
            raise SystemExit(f"dataset row needs 'input' and 'answer': {line[:80]}")
        rows.append({"input": item["input"], "answer": str(item["answer"])})
    if len(rows) < 4:
        raise SystemExit("need at least 4 rows — GEPA cannot reflect on a single example")
    return rows


def dedupe_dataset(rows: list[dict], max_conflict_samples: int = 5) -> tuple[list[dict], dict]:
    """Collapse repeated `input` rows and report label conflicts.

    Why this step exists (it is not cosmetic):

    * **Leakage.** The train/val split is a slice of the file. If one request appears twice,
      the same example is optimised on *and* scored — the validation number goes up while the
      prompt gets no better.
    * **Memorisation.** Reflective optimizers (GEPA included) read traces and rewrite
      instructions in natural language; fed the same row five times, the reflector explains
      *that row* instead of the rule behind it. Repeated data hurts MoE-based models hardest.
    * **Cost.** Every duplicate is another paid rollout against a budget you declared up front.

    Duplicates are matched on the input with whitespace collapsed and case folded. When the
    copies disagree on `answer` (label noise — often a genuinely two-way case in the set),
    the majority label wins and ties keep the first occurrence; every conflicting group is
    reported so the set can be fixed at the source rather than silently averaged away.
    """
    groups: dict[str, list[dict]] = {}
    order: list[str] = []
    for row in rows:
        key = " ".join(row["input"].split()).casefold()
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(row)

    unique: list[dict] = []
    conflicts: list[dict] = []
    for key in order:
        copies = groups[key]
        if len(copies) == 1:
            unique.append(copies[0])
            continue
        counts: dict[str, int] = {}
        for copy in copies:
            counts[copy["answer"]] = counts.get(copy["answer"], 0) + 1
        winner = max(counts, key=lambda a: (counts[a], -list(counts).index(a)))
        unique.append({"input": copies[0]["input"], "answer": winner})
        if len(counts) > 1:
            conflicts.append({
                "input": copies[0]["input"][:160],
                "labels": counts,
                "kept": winner,
                "copies": len(copies),
            })

    stats = {
        "rows_in": len(rows),
        "rows_kept": len(unique),
        "duplicates_removed": len(rows) - len(unique),
        "conflict_groups": len(conflicts),
        "conflicts": conflicts[:max_conflict_samples],
    }
    return unique, stats


def load_evaluator(path: str | None):
    """Custom metric: a module exposing evaluate(data, response) -> (score, feedback|str)."""
    if not path:
        def exact(data, response: str):
            answer = data["answer"]
            got = response or ""
            score = 1.0 if answer.strip().lower() in got.strip().lower() else 0.0
            feedback = ("" if score else f"expected {answer!r}, got {got[:160]!r}")
            return score, feedback
        return exact
    import importlib.util
    spec = importlib.util.spec_from_file_location("tuner_metric", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "evaluate"):
        raise SystemExit(f"{path} must define evaluate(data, response)")
    return module.evaluate


def extract_section(text: str, heading: str | None) -> tuple[str, str, str]:
    """Split a markdown file into (before, section_body, after) around *heading*."""
    if not heading:
        return "", text, ""
    lines = text.splitlines(keepends=True)
    start = None
    for idx, line in enumerate(lines):
        if line.strip().startswith(heading):
            start = idx
            break
    if start is None:
        raise SystemExit(f"section {heading!r} not found in the file")
    end = len(lines)
    for idx in range(start + 1, len(lines)):
        if lines[idx].startswith("## "):
            end = idx
            break
    return "".join(lines[:start + 1]), "".join(lines[start + 1:end]), "".join(lines[end:])


def main() -> int:
    parser = argparse.ArgumentParser(description="GEPA-optimize a prompt or skill section")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--prompt-file", help="plain-text prompt file")
    source.add_argument("--skill", help="SKILL.md to optimize (use with --section)")
    parser.add_argument("--section", help="heading (e.g. '## Rules') whose body is optimized")
    parser.add_argument("--dataset", required=True, help="JSONL with input/answer rows")
    parser.add_argument("--evaluator", help="python file with evaluate(data, response)")
    parser.add_argument("--task-lm", default=DEFAULT_TASK_LM)
    parser.add_argument("--reflection-lm", default=DEFAULT_REFLECTION_LM)
    parser.add_argument("--val-fraction", type=float, default=0.3)
    parser.add_argument("--max-metric-calls", type=int, default=100)
    parser.add_argument("--keep-duplicates", action="store_true",
                        help="do NOT collapse repeated inputs (default: collapse them)")
    parser.add_argument("--max-conflict-samples", type=int, default=5,
                        help="how many label-conflict groups to keep in the report")
    parser.add_argument("--out", default="gepa-report.json")
    parser.add_argument("--write", action="store_true",
                        help="write the best prompt back into --prompt-file/--skill")
    args = parser.parse_args()

    if not os.environ.get("OPENROUTER_API_KEY") and args.task_lm.startswith("openrouter/"):
        env = Path.home() / ".hermes" / ".env"
        if env.exists():
            for line in env.read_text().splitlines():
                if line.startswith("OPENROUTER_API_KEY="):
                    os.environ["OPENROUTER_API_KEY"] = line.split("=", 1)[1].strip().strip('"')
    if args.task_lm.startswith("openrouter/") and not os.environ.get("OPENROUTER_API_KEY"):
        print("no OPENROUTER_API_KEY (env or ~/.hermes/.env)", file=sys.stderr)
        return 2

    import gepa
    from gepa.adapters.default_adapter.default_adapter import EvaluationResult

    if args.skill:
        before, seed, after = extract_section(Path(args.skill).read_text(encoding="utf-8"),
                                              args.section)
    else:
        before, after, seed = "", "", Path(args.prompt_file).read_text(encoding="utf-8")

    metric = load_evaluator(args.evaluator)
    rows = load_dataset(args.dataset)
    if args.keep_duplicates:
        dataset_stats = {
            "rows_in": len(rows), "rows_kept": len(rows), "duplicates_removed": 0,
            "conflict_groups": 0, "conflicts": [], "dedupe_skipped": True,
        }
    else:
        rows, dataset_stats = dedupe_dataset(rows, args.max_conflict_samples)
        if dataset_stats["duplicates_removed"]:
            print(f"dataset: {dataset_stats['rows_in']} rows -> {dataset_stats['rows_kept']} "
                  f"after dropping {dataset_stats['duplicates_removed']} duplicate inputs "
                  f"({dataset_stats['conflict_groups']} with conflicting labels)",
                  file=sys.stderr)
        for conflict in dataset_stats["conflicts"]:
            print(f"  conflict: kept {conflict['kept']!r} out of {conflict['labels']} for "
                  f"{conflict['input'][:80]!r}", file=sys.stderr)
        if len(rows) < 4:
            raise SystemExit("fewer than 4 unique rows after dedupe — nothing to reflect on")

    split = max(1, int(len(rows) * (1 - args.val_fraction)))
    trainset, valset = rows[:split], rows[split:] or rows[-1:]

    def evaluator(data, response):
        score, feedback = metric(data, response)
        return EvaluationResult(score=float(score), feedback=feedback or "", objective_scores=None)

    started = time.time()
    result = gepa.optimize(
        seed_candidate={"prompt": seed},
        trainset=trainset, valset=valset,
        task_lm=args.task_lm, reflection_lm=args.reflection_lm,
        evaluator=evaluator,
        max_metric_calls=args.max_metric_calls,
        skip_perfect_score=False,
        display_progress_bar=False,
        seed=0,
    )
    best = result.best_candidate["prompt"]
    try:
        seed_score = result.val_aggregate_scores[0]
    except Exception:
        seed_score = None
    try:
        best_score = result.val_aggregate_scores[result.best_idx]
    except Exception:
        best_score = None

    diff = "".join(difflib.unified_diff(seed.splitlines(keepends=True),
                                        best.splitlines(keepends=True),
                                        fromfile="seed", tofile="optimized"))
    report = {
        "source": args.skill or args.prompt_file,
        "section": args.section,
        "elapsed_s": round(time.time() - started, 1),
        "task_lm": args.task_lm, "reflection_lm": args.reflection_lm,
        "trainset": len(trainset), "valset": len(valset),
        "dataset": dataset_stats,
        "metric_calls": args.max_metric_calls,
        "candidates": len(result.candidates),
        "val_scores": list(getattr(result, "val_aggregate_scores", []) or []),
        "seed_prompt": seed, "best_prompt": best,
        "diff": diff, "changed": bool(diff.strip()),
    }
    Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items()
                      if k not in ("seed_prompt", "best_prompt", "diff")}, indent=2))
    if report["changed"]:
        print("\n--- diff (seed -> optimized) ---\n" + diff)
    else:
        print("\nNo prompt change survived validation — the seed is already at the ceiling "
              "for this task set. Pick a task with a real failure rate before spending more.")
    if args.write and report["changed"]:
        if args.skill:
            Path(args.skill).write_text(before + best + ("" if best.endswith("\n") else "\n")
                                        + after, encoding="utf-8")
        else:
            Path(args.prompt_file).write_text(best, encoding="utf-8")
        print(f"\nwritten back to {args.skill or args.prompt_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
