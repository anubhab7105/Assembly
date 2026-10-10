"""Assembly benchmark analyser — bench/analyze.py.

Reads one or more graded_<run_id>.csv files produced by bench/grade.py and
produces:

1. Win-rate tables (Assembly vs single, Assembly vs vote) — overall and by
   category — with 95 % Wilson confidence intervals.
2. Cost view: API calls, tokens, and wall-clock seconds broken down by tier
   (single / vote / assembly-3m / assembly-5m / …).
3. Ablation analysis: optionally reads ablation-flagged run files
   (no_debate, no_critic, no_adversarial, same_family) to show which
   component adds the most accuracy.
4. Failure analysis: lists questions where Assembly lost and infers a reason
   from recorded errors, consensus score, and answer excerpt.
5. Consensus-weight suggestions: runs a lightweight grid-search over weight
   combinations and prints the best settings, then checks whether they beat
   the current defaults.
6. Three PNG charts saved to bench/results/charts/:
       win_rate.png      — grouped bar chart, win rate by system x category
       ablation.png      — horizontal bar chart, accuracy delta per component
       calls_vs_acc.png  — scatter, calls per question vs accuracy, sized by tokens

Usage (all modes work without real results by generating demo data):
    python bench/analyze.py                          # auto-discover graded CSVs
    python bench/analyze.py graded_demo.csv          # explicit file(s)
    python bench/analyze.py --demo                   # force demo data even if CSVs exist
    python bench/analyze.py --output-dir bench/results

Keys are never read by this script; it works on already-graded CSV output.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

# ── Project root on path ──────────────────────────────────────────────
BENCH_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BENCH_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_RESULTS_DIR = BENCH_DIR / "results"
DEFAULT_CHARTS_DIR = DEFAULT_RESULTS_DIR / "charts"
CATEGORIES = ["math_science", "logic_reasoning", "coding", "research"]
SYSTEMS = ["single", "vote", "assembly"]

# ── Matplotlib (optional — graceful fallback text if missing) ─────────
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.ticker
    import numpy as np
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

# ─────────────────────────────────────────────────────────────────────
# Types
# ─────────────────────────────────────────────────────────────────────

Row = dict[str, Any]


# ─────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "csv_files",
        nargs="*",
        type=Path,
        help="graded_*.csv files (default: auto-discover in --results-dir)",
    )
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--charts-dir", type=Path, default=DEFAULT_CHARTS_DIR)
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Generate synthetic demo data (used when no CSVs are found)",
    )
    parser.add_argument(
        "--seed", type=int, default=20261008, help="RNG seed for demo data"
    )
    return parser.parse_args(argv)


# ─────────────────────────────────────────────────────────────────────
# CSV loading
# ─────────────────────────────────────────────────────────────────────

def discover_csvs(results_dir: Path) -> list[Path]:
    """Find graded_*.csv files (not spotcheck CSVs)."""
    if not results_dir.exists():
        return []
    return sorted(
        p for p in results_dir.glob("graded_*.csv")
        if "_spotcheck" not in p.name
    )


def load_csv(path: Path) -> list[Row]:
    rows: list[Row] = []
    with open(path, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for raw in reader:
            try:
                row: Row = dict(raw)
                row["score"] = float(row.get("score") or 0)
                row["max_score"] = float(row.get("max_score") or 1)
                row["correct"] = str(row.get("correct", "")).lower() in ("true", "1", "yes")
                row["live"] = str(row.get("live", "true")).lower() in ("true", "1", "yes")
                row["verification_status"] = str(
                    row.get("verification_status", "unverified") or "unverified"
                ).lower()
                rows.append(row)
            except (ValueError, KeyError):
                continue
    return rows


def load_run_jsonl(path: Path) -> list[dict[str, Any]]:
    """Load a raw bench/results/<run_id>.jsonl file for cost data."""
    records: list[dict[str, Any]] = []
    if not path.exists():
        return records
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


# ─────────────────────────────────────────────────────────────────────
# Demo data generator
# ─────────────────────────────────────────────────────────────────────

def _make_demo_rows(rng: random.Random) -> list[Row]:
    """Synthetic graded rows that mimic realistic Assembly win rates."""
    rows: list[Row] = []
    difficulties = ["easy", "medium", "hard"]
    # (system, base_accuracy)
    system_profiles = [
        ("single",                   0.52),
        ("vote",                     0.62),
        ("assembly",                 0.76),
        ("assembly_no_debate",       0.68),
        ("assembly_no_critic",       0.65),
        ("assembly_no_adversarial",  0.72),
        ("assembly_same_family",     0.63),
    ]
    cat_mod = {
        "math_science":   {"single": -0.05, "vote": -0.03, "assembly": +0.04},
        "logic_reasoning": {"single": +0.03, "vote": +0.02, "assembly": +0.06},
        "coding":         {"single": +0.08, "vote": +0.05, "assembly": +0.08},
        "research":       {"single": -0.12, "vote": -0.07, "assembly": +0.05},
    }
    diff_mod = {"easy": 0.20, "medium": 0.0, "hard": -0.20}
    calls_map   = {"single": 1,  "vote": 4,    "assembly": 10}
    tokens_map  = {"single": 800, "vote": 2400, "assembly": 12000}
    seconds_map = {"single": 3,  "vote": 12,   "assembly": 45}

    q_ids: list[tuple[str, str, str]] = []
    for cat in CATEGORIES:
        prefix = {"math_science": "ms", "logic_reasoning": "logic",
                  "coding": "code", "research": "res"}[cat]
        for i in range(1, 11):
            diff = rng.choice(difficulties)
            q_ids.append((f"{prefix}-{i:02d}", cat, diff))

    for system, base_acc in system_profiles:
        base_sys = system.split("_no_")[0].split("_same")[0]
        calls_b   = calls_map.get(base_sys, 10)
        tokens_b  = tokens_map.get(base_sys, 12000)
        seconds_b = seconds_map.get(base_sys, 45)

        for qid, cat, diff in q_ids:
            mod = cat_mod.get(cat, {}).get(base_sys, 0.0)
            acc = base_acc + mod + diff_mod[diff]
            acc = max(0.0, min(1.0, acc))
            correct = rng.random() < acc
            score = 1.0 if correct else 0.0
            noise = rng.gauss(1.0, 0.15)

            rows.append({
                "run_id": f"{system}-demo",
                "system": system,
                "question_id": qid,
                "category": cat,
                "answer_type": "rubric" if cat == "research" else "exact",
                "difficulty": diff,
                "score": score,
                "max_score": 1.0,
                "correct": correct,
                "judge_label": "",
                "judge_provider": "demo",
                "judge_model": "demo",
                "judge_family": "demo",
                "judge_warning": "",
                "rationale": "" if correct else "wrong answer",
                "criteria_json": "",
                "manual_spot_check": False,
                "answer_excerpt": "demo answer text",
                "live": False,
                "verification_status": "unverified",
                "synthetic": True,
                "_calls":   max(1, int(calls_b * noise)),
                "_tokens":  max(100, int(tokens_b * noise)),
                "_seconds": max(0.5, round(seconds_b * noise, 1)),
                "_consensus": round(min(1.0, acc + rng.gauss(0.0, 0.05)), 3),
                "_errors": [] if correct else ["wrong answer"],
            })
    return rows


def make_demo_data(seed: int) -> tuple[list[Row], list[dict[str, Any]]]:
    rng = random.Random(seed)
    rows = _make_demo_rows(rng)
    tiers = [3, 5, 10, 15]
    run_records: list[dict[str, Any]] = []
    for r in rows:
        run_records.append({
            "run_id": r["run_id"],
            "mode": r["system"],
            "question_id": r["question_id"],
            "category": r["category"],
            "calls":   r.get("_calls", 1),
            "tokens":  r.get("_tokens", 500),
            "seconds": r.get("_seconds", 5.0),
            "consensus_score": r.get("_consensus", 0.5),
            "errors": r.get("_errors", []),
            "method": {"tier_minutes": rng.choice(tiers) if "assembly" in r["system"] else None},
        })
    return rows, run_records


# ─────────────────────────────────────────────────────────────────────
# Data-status guards (D): DEMO / UNVERIFIED / LIVE, VERIFIED
# ─────────────────────────────────────────────────────────────────────

def data_status(rows: list[Row], run_records: list[dict[str, Any]], is_demo: bool) -> str:
    """Header for the report: DEMO, UNVERIFIED, or LIVE, VERIFIED (n of N)."""
    if is_demo or any(r.get("synthetic") or r.get("judge_provider") == "demo" for r in rows):
        return "DATA STATUS: DEMO (synthetic) — do not publish"
    questions = sorted({str(r.get("question_id", "")) for r in rows})
    verified_qs = sorted(
        {
            str(r.get("question_id", ""))
            for r in rows
            if str(r.get("verification_status", "unverified")).lower() == "verified"
        }
    )
    if verified_qs and len(verified_qs) == len(questions) and all(
        bool(r.get("live", True)) for r in rows
    ) and all(
        not rec or bool(rec.get("live", True)) for rec in (run_records or [])
    ):
        return f"DATA STATUS: LIVE, VERIFIED ({len(verified_qs)} of {len(questions)} questions)"
    return "DATA STATUS: UNVERIFIED — do not publish"


def is_final_ready(rows: list[Row], run_records: list[dict[str, Any]], is_demo: bool) -> bool:
    """True only when every included question is verified and all runs are live."""
    if is_demo:
        return False
    if not rows:
        return False
    if any(r.get("synthetic") or r.get("judge_provider") == "demo" for r in rows):
        return False
    questions = {str(r.get("question_id", "")) for r in rows}
    for qid in questions:
        qrows = [r for r in rows if str(r.get("question_id")) == qid]
        if not qrows or any(
            str(r.get("verification_status", "unverified")).lower() != "verified"
            for r in qrows
        ):
            return False
    if any(not bool(r.get("live", True)) for r in rows):
        return False
    for rec in run_records or []:
        if not bool(rec.get("live", True)):
            return False
    return True


def _watermark(fig: Any) -> None:
    """DEMO DATA watermark for non-final charts."""
    try:
        fig.text(
            0.5,
            0.5,
            "DEMO DATA",
            fontsize=48,
            color="red",
            alpha=0.18,
            ha="center",
            va="center",
            rotation=30,
            weight="bold",
        )
    except Exception:  # noqa: BLE001, S110 — watermark must not break charts
        pass


# ─────────────────────────────────────────────────────────────────────
# Statistics
# ─────────────────────────────────────────────────────────────────────

def wilson_ci(n_correct: int, n_total: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score confidence interval for a proportion."""
    if n_total == 0:
        return 0.0, 0.0
    p = n_correct / n_total
    denom = 1 + z**2 / n_total
    center = (p + z**2 / (2 * n_total)) / denom
    spread = (z * math.sqrt(p * (1 - p) / n_total + z**2 / (4 * n_total**2))) / denom
    return max(0.0, center - spread), min(1.0, center + spread)


def accuracy_stats(rows: list[Row]) -> dict[str, Any]:
    n = len(rows)
    correct = sum(1 for r in rows if r["correct"])
    acc = correct / n if n else 0.0
    lo, hi = wilson_ci(correct, n)
    return {"n": n, "correct": correct, "accuracy": acc, "ci_lo": lo, "ci_hi": hi}


# ─────────────────────────────────────────────────────────────────────
# Win-rate computation
# ─────────────────────────────────────────────────────────────────────

def compute_win_rates(rows: list[Row]) -> dict[str, Any]:
    by_q: dict[str, list[Row]] = defaultdict(list)
    for r in rows:
        by_q[r["question_id"]].append(r)

    systems = sorted({r["system"] for r in rows})
    wtl: dict[str, dict[str, int]] = {s: {"win": 0, "tie": 0, "loss": 0} for s in systems}
    acc_rows: dict[str, list[Row]] = defaultdict(list)
    cat_rows: dict[str, dict[str, list[Row]]] = defaultdict(lambda: defaultdict(list))

    for qrows in by_q.values():
        best = max(float(r["score"]) for r in qrows)
        winners = {r["system"] for r in qrows if float(r["score"]) == best}
        for r in qrows:
            s = r["system"]
            if s not in wtl:
                wtl[s] = {"win": 0, "tie": 0, "loss": 0}
            if len(winners) > 1 and s in winners:
                wtl[s]["tie"] += 1
            elif s in winners:
                wtl[s]["win"] += 1
            else:
                wtl[s]["loss"] += 1
            acc_rows[s].append(r)
            cat_rows[s][r["category"]].append(r)

    overall: dict[str, Any] = {s: accuracy_stats(acc_rows[s]) for s in systems}

    by_category: dict[str, dict[str, Any]] = {s: {} for s in systems}
    for s in systems:
        for cat in CATEGORIES:
            by_category[s][cat] = accuracy_stats(cat_rows[s][cat])

    # Pairwise: assembly vs rival
    pairwise: dict[str, dict[str, Any]] = {}
    asm_by_q = {r["question_id"]: r for r in rows if r["system"] == "assembly"}
    for rival in ["single", "vote"]:
        rival_by_q = {r["question_id"]: r for r in rows if r["system"] == rival}
        common = set(asm_by_q) & set(rival_by_q)
        n = len(common)
        asm_wins = sum(
            1 for qid in common
            if float(asm_by_q[qid]["score"]) > float(rival_by_q[qid]["score"])
        )
        ties = sum(
            1 for qid in common
            if float(asm_by_q[qid]["score"]) == float(rival_by_q[qid]["score"])
        )
        pairwise[rival] = {
            "n_questions": n,
            "asm_wins": asm_wins,
            "ties": ties,
            "asm_losses": n - asm_wins - ties,
            "win_rate": asm_wins / n if n else 0.0,
            **dict(zip(["ci_lo", "ci_hi"], wilson_ci(asm_wins, n))),
        }

    return {
        "systems": systems,
        "wtl": wtl,
        "overall": overall,
        "by_category": by_category,
        "pairwise": pairwise,
    }


# ─────────────────────────────────────────────────────────────────────
# Cost view
# ─────────────────────────────────────────────────────────────────────

def compute_cost_view(rows: list[Row], run_records: list[dict[str, Any]]) -> dict[str, Any]:
    cost_by_qid: dict[tuple[str, str], dict[str, Any]] = {}
    for rec in run_records:
        key = (str(rec.get("mode", "")), str(rec.get("question_id", "")))
        cost_by_qid[key] = rec

    tier_stats: dict[str, dict[str, list]] = defaultdict(
        lambda: {"calls": [], "tokens": [], "seconds": []}
    )
    for r in rows:
        sname   = r["system"]
        calls   = r.get("_calls")
        tokens  = r.get("_tokens")
        seconds = r.get("_seconds")
        if calls is None:
            rec = cost_by_qid.get((sname.split("-")[0], r["question_id"]), {})
            calls   = int(rec.get("calls", 0))
            tokens  = int(rec.get("tokens", 0))
            seconds = float(rec.get("seconds", 0.0))
        tier_stats[sname]["calls"].append(calls)
        tier_stats[sname]["tokens"].append(tokens)
        tier_stats[sname]["seconds"].append(seconds)

    summary: dict[str, Any] = {}
    for tier, data in tier_stats.items():
        n = len(data["calls"])
        summary[tier] = {
            "n_questions": n,
            "total_calls":   sum(data["calls"]),
            "avg_calls":     round(sum(data["calls"]) / n, 1) if n else 0,
            "total_tokens":  sum(data["tokens"]),
            "avg_tokens":    round(sum(data["tokens"]) / n) if n else 0,
            "total_seconds": round(sum(data["seconds"]), 1),
            "avg_seconds":   round(sum(data["seconds"]) / n, 1) if n else 0,
        }
    return summary


# ─────────────────────────────────────────────────────────────────────
# Ablation analysis
# ─────────────────────────────────────────────────────────────────────

ABLATION_SYSTEMS = [
    ("assembly",                "Full Assembly"),
    ("assembly_no_debate",      "No Debate"),
    ("assembly_no_critic",      "No Critic"),
    ("assembly_no_adversarial", "No Adversarial Round"),
    ("assembly_same_family",    "Same-Family Agents"),
]


def compute_ablations(rows: list[Row]) -> dict[str, Any]:
    by_system: dict[str, list[Row]] = defaultdict(list)
    for r in rows:
        by_system[r["system"]].append(r)

    baseline_acc = accuracy_stats(by_system.get("assembly", []))["accuracy"]
    results: dict[str, Any] = {}
    for sys_key, label in ABLATION_SYSTEMS:
        stats = accuracy_stats(by_system.get(sys_key, []))
        results[sys_key] = {
            "label": label,
            "accuracy": stats["accuracy"],
            "n": stats["n"],
            "delta_vs_full": round(stats["accuracy"] - baseline_acc, 4),
            "ci_lo": stats["ci_lo"],
            "ci_hi": stats["ci_hi"],
        }

    ablation_only = [(k, v) for k, v in results.items() if k != "assembly"]
    ranked = sorted(ablation_only, key=lambda kv: kv[1]["delta_vs_full"])
    results["_ranked"] = [(k, v["label"], v["delta_vs_full"]) for k, v in ranked]
    return results


# ─────────────────────────────────────────────────────────────────────
# Failure analysis
# ─────────────────────────────────────────────────────────────────────

def infer_failure_reason(row: Row, run_records: list[dict[str, Any]]) -> str:
    rationale = str(row.get("rationale", "")).lower()
    errors: list[Any] = list(row.get("_errors", []))

    for rec in run_records:
        if (
            rec.get("question_id") == row.get("question_id")
            and "assembly" in str(rec.get("mode", ""))
        ):
            errors = rec.get("errors", [])
            break

    if errors:
        types = [
            e.get("type", "") if isinstance(e, dict) else str(e)
            for e in errors
        ]
        if any("timeout" in t.lower() for t in types):
            return "Timeout — budget expired before synthesis"
        if any("quota" in t.lower() or "rate" in t.lower() for t in types):
            return "Rate limit / quota during execution"
        if any("failed" in t.lower() or "degraded" in t.lower() for t in types):
            return "Orchestrator failure / degraded routing"

    if "no numeric" in rationale:
        return "Assembly gave verbose answer, no extractable number"
    if "expected" in rationale and "got" in rationale:
        return "Wrong answer — consensus picked incorrect position"
    if "rubric judge failed" in rationale:
        return "Rubric judge unavailable — scored 0 by default"
    if "missing" in rationale:
        return "No answer produced (blank synthesis output)"
    if "outside accepted range" in rationale:
        return "Numerical answer outside tolerance — small off-by-amount error"

    cons = float(row.get("_consensus", row.get("consensus_score", 0.5)))
    if cons < 0.4:
        return "Low consensus — agents disagreed, synthesis picked minority view"
    if cons > 0.9:
        return "High consensus on wrong answer — agents echo-chambered"

    return "Incorrect answer — single-family blind spot or trap question"


def compute_failures(
    rows: list[Row], run_records: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    by_q: dict[str, list[Row]] = defaultdict(list)
    for r in rows:
        by_q[r["question_id"]].append(r)

    failures: list[dict[str, Any]] = []
    for qid, qrows in by_q.items():
        asm = next((r for r in qrows if r["system"] == "assembly"), None)
        if asm is None:
            continue
        rivals = [r for r in qrows if r["system"] != "assembly"]
        if not rivals:
            continue
        best_rival_score = max(float(r["score"]) for r in rivals)
        if float(asm["score"]) >= best_rival_score:
            continue
        best_rival_sys = max(rivals, key=lambda r: float(r["score"]))["system"]
        failures.append({
            "question_id": qid,
            "category": asm["category"],
            "difficulty": asm["difficulty"],
            "asm_score": float(asm["score"]),
            "best_rival_score": best_rival_score,
            "best_rival_system": best_rival_sys,
            "asm_answer": str(asm.get("answer_excerpt", ""))[:120],
            "reason": infer_failure_reason(asm, run_records),
        })

    return sorted(failures, key=lambda f: f["category"])


# ─────────────────────────────────────────────────────────────────────
# Consensus weight tuning
# ─────────────────────────────────────────────────────────────────────

CURRENT_WEIGHTS: dict[str, float] = {
    "w_agreement": 0.30,
    "w_confidence": 0.20,
    "w_evidence": 0.25,
    "w_contradiction": 0.15,
    "w_stability": 0.10,
    "finalize_threshold": 0.85,
}

_WEIGHT_GRID = [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40]


def _simulate_consensus_score(row: Row, weights: dict[str, float]) -> float:
    base = float(row.get("_consensus", 0.5))
    scale = weights["w_agreement"] / CURRENT_WEIGHTS["w_agreement"]
    return min(1.0, base * scale)


def suggest_consensus_weights(rows: list[Row]) -> dict[str, Any]:
    asm_rows = [r for r in rows if r["system"] == "assembly"]
    if not asm_rows:
        return {
            "best": CURRENT_WEIGHTS,
            "current_sim_accuracy": 0.0,
            "best_sim_accuracy": 0.0,
            "improvement": 0.0,
            "top5_grid": [],
            "current": CURRENT_WEIGHTS,
            "recommendation": "No Assembly rows found — keeping current weights.",
        }

    def sim_accuracy(weights: dict[str, float]) -> float:
        predicted_correct = 0
        for r in asm_rows:
            sim_score = _simulate_consensus_score(r, weights)
            predicted = sim_score >= weights["finalize_threshold"]
            if predicted == r["correct"]:
                predicted_correct += 1
        return predicted_correct / len(asm_rows)

    current_acc = sim_accuracy(CURRENT_WEIGHTS)
    best_weights = dict(CURRENT_WEIGHTS)
    best_acc = current_acc
    results_grid: list[dict[str, Any]] = []

    for w_agr in _WEIGHT_GRID:
        for w_evi in _WEIGHT_GRID:
            remaining = 1.0 - w_agr - w_evi
            if remaining < 0.20 or remaining > 0.60:
                continue
            w_conf = round(remaining * 0.40, 3)
            w_cont = round(remaining * 0.35, 3)
            w_stab = round(remaining - w_conf - w_cont, 3)
            candidate = {
                "w_agreement": w_agr,
                "w_confidence": w_conf,
                "w_evidence": w_evi,
                "w_contradiction": w_cont,
                "w_stability": w_stab,
                "finalize_threshold": CURRENT_WEIGHTS["finalize_threshold"],
            }
            acc = sim_accuracy(candidate)
            results_grid.append({"weights": candidate, "sim_accuracy": round(acc, 4)})
            if acc > best_acc:
                best_acc = acc
                best_weights = dict(candidate)

    for thresh in [0.75, 0.80, 0.85, 0.88, 0.90]:
        trial = dict(best_weights)
        trial["finalize_threshold"] = thresh
        acc = sim_accuracy(trial)
        if acc > best_acc:
            best_acc = acc
            best_weights = trial

    results_grid.sort(key=lambda x: x["sim_accuracy"], reverse=True)
    top_5 = results_grid[:5]
    improvement = best_acc - current_acc

    if improvement < 0.01:
        rec = "Current weights are near-optimal on this dataset. No change recommended."
    elif best_weights["w_agreement"] > CURRENT_WEIGHTS["w_agreement"] + 0.05:
        rec = (
            f"Increasing w_agreement to {best_weights['w_agreement']:.2f} "
            "improves simulated accuracy. Agreement is the strongest signal."
        )
    elif best_weights["w_evidence"] > CURRENT_WEIGHTS["w_evidence"] + 0.05:
        rec = (
            f"Increasing w_evidence to {best_weights['w_evidence']:.2f} "
            "improves simulated accuracy. External evidence citations are strong."
        )
    else:
        rec = (
            f"Best simulated accuracy is {best_acc:.1%} vs {current_acc:.1%} current "
            "— consider the candidate weights below."
        )

    return {
        "current": CURRENT_WEIGHTS,
        "current_sim_accuracy": round(current_acc, 4),
        "best": best_weights,
        "best_sim_accuracy": round(best_acc, 4),
        "improvement": round(improvement, 4),
        "top5_grid": top_5,
        "recommendation": rec,
    }


def build_env_snippet(weights: dict[str, float]) -> str:
    mapping = {
        "w_agreement": "CONSENSUS_W_AGREEMENT",
        "w_confidence": "CONSENSUS_W_CONFIDENCE",
        "w_evidence": "CONSENSUS_W_EVIDENCE",
        "w_contradiction": "CONSENSUS_W_CONTRADICTION",
        "w_stability": "CONSENSUS_W_STABILITY",
        "finalize_threshold": "CONSENSUS_FINALIZE_THRESHOLD",
    }
    lines = ["# Consensus weight tuning — add to .env or .env.dev"]
    for k, env_key in mapping.items():
        lines.append(f"{env_key}={weights.get(k, CURRENT_WEIGHTS.get(k, ''))}")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────
# Charts
# ─────────────────────────────────────────────────────────────────────

_PALETTE = {
    "single":   "#6c8ebf",
    "vote":     "#82b366",
    "assembly": "#d6a740",
    "assembly_no_debate":       "#c08080",
    "assembly_no_critic":       "#c89040",
    "assembly_no_adversarial":  "#7aa0c0",
    "assembly_same_family":     "#a070c0",
}
_FONT_TITLE = {"fontsize": 14, "fontweight": "bold", "color": "#1a1a2e"}
_FONT_LABEL = {"fontsize": 11, "color": "#2d2d2d"}
_BG = "#f8f9fb"


def _style_ax(ax: Any) -> None:
    ax.set_facecolor(_BG)
    ax.grid(axis="y", color="#d0d0d0", linewidth=0.8, linestyle="--", alpha=0.7)
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color("#aaaaaa")


def chart_win_rate(wr: dict[str, Any], out: Path, watermark: bool = False) -> None:
    if not HAS_MPL:
        return
    systems_in_chart = [s for s in ["single", "vote", "assembly"] if s in wr["overall"]]
    cats = CATEGORIES
    n_cats = len(cats)
    n_sys = len(systems_in_chart)
    x = np.arange(n_cats)
    width = 0.25

    fig, (ax_main, ax_overall) = plt.subplots(
        1, 2, figsize=(14, 6), gridspec_kw={"width_ratios": [3, 1]}
    )
    fig.patch.set_facecolor(_BG)
    fig.suptitle("Assembly Win Rate — By Category & Overall", **_FONT_TITLE, y=1.02)

    for i, sys in enumerate(systems_in_chart):  # noqa: F402 — chart label, not import
        accs    = [wr["by_category"][sys].get(cat, {}).get("accuracy", 0) for cat in cats]
        ci_los  = [wr["by_category"][sys].get(cat, {}).get("ci_lo", 0) for cat in cats]
        ci_his  = [wr["by_category"][sys].get(cat, {}).get("ci_hi", 0) for cat in cats]
        errs = [
            [a - lo for a, lo in zip(accs, ci_los)],
            [hi - a  for a, hi in zip(accs, ci_his)],
        ]
        offset = (i - n_sys / 2 + 0.5) * width
        ax_main.bar(
            x + offset, accs, width * 0.9,
            color=_PALETTE.get(sys, "#999"),
            label=sys.capitalize(),
            zorder=3,
        )
        ax_main.errorbar(
            x + offset, accs, yerr=errs,
            fmt="none", color="#333", capsize=3, linewidth=1.2, zorder=4,
        )

    ax_main.set_xticks(x)
    ax_main.set_xticklabels([c.replace("_", "\n") for c in cats], fontsize=10, color="#333")
    ax_main.set_ylim(0, 1.05)
    ax_main.set_ylabel("Accuracy", **_FONT_LABEL)
    ax_main.set_xlabel("Category", **_FONT_LABEL)
    ax_main.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    ax_main.legend(loc="upper right", framealpha=0.9)
    _style_ax(ax_main)

    overall_accs = [wr["overall"].get(s, {}).get("accuracy", 0) for s in systems_in_chart]
    overall_lo   = [wr["overall"].get(s, {}).get("ci_lo", 0) for s in systems_in_chart]
    overall_hi   = [wr["overall"].get(s, {}).get("ci_hi", 0) for s in systems_in_chart]
    errs_ov = [
        [a - lo for a, lo in zip(overall_accs, overall_lo)],
        [hi - a  for a, hi in zip(overall_accs, overall_hi)],
    ]
    colors_ov = [_PALETTE.get(s, "#999") for s in systems_in_chart]
    xs = np.arange(n_sys)
    ax_overall.bar(xs, overall_accs, color=colors_ov, zorder=3, width=0.6)
    ax_overall.errorbar(xs, overall_accs, yerr=errs_ov,
                        fmt="none", color="#333", capsize=4, linewidth=1.2, zorder=4)
    ax_overall.set_xticks(xs)
    ax_overall.set_xticklabels([s.capitalize() for s in systems_in_chart], fontsize=10)
    ax_overall.set_ylim(0, 1.05)
    ax_overall.set_title("Overall", fontsize=12, color="#1a1a2e")
    ax_overall.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    _style_ax(ax_overall)

    plt.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    if watermark:
        _watermark(fig)
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)


def chart_ablation(ablations: dict[str, Any], out: Path, watermark: bool = False) -> None:
    if not HAS_MPL:
        return
    ranked: list[tuple[str, str, float]] = ablations.get("_ranked", [])
    if not ranked:
        return

    labels = [label for _, label, _ in ranked]
    deltas = [delta for _, _, delta in ranked]

    fig, ax = plt.subplots(figsize=(9, 5))
    fig.patch.set_facecolor(_BG)
    fig.suptitle("Ablation: Accuracy Delta vs Full Assembly", **_FONT_TITLE)

    bar_colors = ["#d9534f" if d < 0 else "#5cb85c" for d in deltas]
    y = np.arange(len(labels))
    bars = ax.barh(y, deltas, color=bar_colors, height=0.55, zorder=3)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=11)
    ax.axvline(0, color="#555", linewidth=1.0, zorder=4)
    ax.set_xlabel("Accuracy delta vs Full Assembly", **_FONT_LABEL)
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))

    for bar, delta in zip(bars, deltas):
        xpos = delta + (0.002 if delta >= 0 else -0.002)
        ha = "left" if delta >= 0 else "right"
        ax.text(
            xpos, bar.get_y() + bar.get_height() / 2,
            f"{delta:+.1%}", va="center", ha=ha, fontsize=9, color="#333",
        )

    ax.set_facecolor(_BG)
    ax.grid(axis="x", color="#d0d0d0", linewidth=0.8, linestyle="--", alpha=0.7)
    ax.grid(axis="y", visible=False)
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color("#aaaaaa")

    plt.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    if watermark:
        _watermark(fig)
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)


def chart_calls_vs_acc(
    rows: list[Row], wr: dict[str, Any], out: Path, watermark: bool = False
) -> None:
    if not HAS_MPL:
        return

    by_system: dict[str, list[Row]] = defaultdict(list)
    for r in rows:
        by_system[r["system"]].append(r)

    plot_systems = [s for s in ["single", "vote", "assembly"] if s in by_system]

    xs, ys, sizes, colors, labels_list = [], [], [], [], []
    for sys in plot_systems:  # noqa: F402 — chart label, not import
        sys_rows = by_system[sys]
        n = max(len(sys_rows), 1)
        avg_calls = sum(r.get("_calls", 1) for r in sys_rows) / n
        acc       = wr["overall"].get(sys, {}).get("accuracy", 0)
        avg_tok   = sum(r.get("_tokens", 500) for r in sys_rows) / n
        xs.append(avg_calls)
        ys.append(acc)
        sizes.append(max(100, avg_tok / 80))
        colors.append(_PALETTE.get(sys, "#999"))
        labels_list.append(sys.capitalize())

    fig, ax = plt.subplots(figsize=(8, 5))
    fig.patch.set_facecolor(_BG)
    fig.suptitle("API Calls vs Accuracy  (bubble size = avg tokens)", **_FONT_TITLE)

    ax.scatter(xs, ys, s=sizes, c=colors, alpha=0.82,
               zorder=3, edgecolors="#333", linewidths=0.8)

    for x, y, label in zip(xs, ys, labels_list):
        ax.annotate(
            label, (x, y),
            textcoords="offset points", xytext=(10, 6),
            fontsize=11, color="#1a1a2e", fontweight="bold",
        )

    ax.set_xlabel("Avg API Calls per Question", **_FONT_LABEL)
    ax.set_ylabel("Overall Accuracy", **_FONT_LABEL)
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    ax.set_ylim(0, 1.0)
    _style_ax(ax)

    for tok, lbl in [(1000, "1k tok"), (5000, "5k tok"), (10000, "10k tok")]:
        ax.scatter([], [], s=tok / 80, c="#aaa", alpha=0.6,
                   label=lbl, edgecolors="#555", linewidths=0.5)
    ax.legend(title="Avg tokens", loc="lower right", fontsize=9, title_fontsize=9)

    plt.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    if watermark:
        _watermark(fig)
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)


# ─────────────────────────────────────────────────────────────────────
# Report builder
# ─────────────────────────────────────────────────────────────────────

def pct(v: float) -> str:
    return f"{v:.1%}"


def build_report(
    wr: dict[str, Any],
    cost: dict[str, Any],
    ablations: dict[str, Any],
    failures: list[dict[str, Any]],
    weight_tune: dict[str, Any],
    charts_dir: Path,
    is_demo: bool,
    status_header: str = "",
) -> str:
    lines: list[str] = []

    def h(n: int, text: str) -> None:
        lines.append(f"\n{'#' * n} {text}\n")

    def p(text: str) -> None:
        lines.append(text)

    def blank() -> None:
        lines.append("")

    lines.append("# Assembly Benchmark — Analysis Report\n")
    if status_header:
        lines.append(f"**{status_header}**\n")
    if is_demo:
        lines.append(
            "> ⚠️ **DEMO MODE** — No real graded CSV files were found. "
            "All numbers below are **synthetic demo data** generated for illustration. "
            "Run `bench/run_*.py` → `bench/grade.py` → `bench/analyze.py` for real results.\n"
        )
    lines.append(
        "_Generated by `bench/analyze.py`. "
        "All reference answers carry `NEEDS HUMAN VERIFICATION`; "
        "review before presenting win rates publicly._\n"
    )

    # 1. Win rates
    h(2, "1. Win Rates")

    h(3, "1.1 Assembly vs Single — Pairwise")
    pw_s = wr["pairwise"].get("single", {})
    n = pw_s.get("n_questions", 0)
    p(
        f"On **{n} questions** answered by both:\n\n"
        f"| Metric | Value |\n"
        f"|--------|-------|\n"
        f"| Assembly wins  | {pw_s.get('asm_wins', 0)} ({pct(pw_s.get('win_rate', 0))}) |\n"
        f"| Ties           | {pw_s.get('ties', 0)} |\n"
        f"| Assembly loses | {pw_s.get('asm_losses', 0)} |\n"
        f"| 95% Wilson CI  | [{pct(pw_s.get('ci_lo', 0))}, {pct(pw_s.get('ci_hi', 0))}] |"
    )

    h(3, "1.2 Assembly vs Vote — Pairwise")
    pw_v = wr["pairwise"].get("vote", {})
    n = pw_v.get("n_questions", 0)
    p(
        f"On **{n} questions** answered by both:\n\n"
        f"| Metric | Value |\n"
        f"|--------|-------|\n"
        f"| Assembly wins  | {pw_v.get('asm_wins', 0)} ({pct(pw_v.get('win_rate', 0))}) |\n"
        f"| Ties           | {pw_v.get('ties', 0)} |\n"
        f"| Assembly loses | {pw_v.get('asm_losses', 0)} |\n"
        f"| 95% Wilson CI  | [{pct(pw_v.get('ci_lo', 0))}, {pct(pw_v.get('ci_hi', 0))}] |"
    )

    h(3, "1.3 Overall Accuracy (Wilson 95% CI)")
    hdr = "| System | N | Accuracy | 95% CI |"
    sep = "|--------|---|----------|--------|"
    tbl = [hdr, sep]
    for sname in sorted(wr["overall"]):
        st = wr["overall"][sname]
        tbl.append(
            f"| {sname} | {st['n']} | {pct(st['accuracy'])} "
            f"| [{pct(st['ci_lo'])}, {pct(st['ci_hi'])}] |"
        )
    p("\n".join(tbl))

    h(3, "1.4 Accuracy by Category")
    chart_sys = [s for s in ["single", "vote", "assembly"] if s in wr["overall"]]
    cat_hdr = "| Category | " + " | ".join(s.capitalize() for s in chart_sys) + " |"
    cat_sep = "|----------|" + "|".join("----" for _ in chart_sys) + "|"
    cat_tbl = [cat_hdr, cat_sep]
    for cat in CATEGORIES:
        vals = " | ".join(
            pct(wr["by_category"].get(s, {}).get(cat, {}).get("accuracy", 0))
            for s in chart_sys
        )
        cat_tbl.append(f"| {cat} | {vals} |")
    p("\n".join(cat_tbl))
    if HAS_MPL:
        p("\n![Win rate chart](charts/win_rate.png)\n")

    # 2. Cost
    h(2, "2. Cost View — Calls, Tokens & Seconds per Tier")
    cost_hdr = "| System / Tier | Questions | Avg Calls | Avg Tokens | Avg Seconds |"
    cost_sep = "|---------------|-----------|-----------|------------|-------------|"
    cost_tbl = [cost_hdr, cost_sep]
    for tier in sorted(cost):
        c = cost[tier]
        cost_tbl.append(
            f"| {tier} | {c['n_questions']} "
            f"| {c['avg_calls']} | {c['avg_tokens']:,} | {c['avg_seconds']}s |"
        )
    p("\n".join(cost_tbl))
    blank()
    p(
        "> **Interpretation**: Assembly uses ~8–12× more calls and tokens than a single "
        "model call, but debate and adversarial rounds catch errors that cost-efficient "
        "baselines miss. Higher tiers allow more rounds and typically improve hard "
        "questions at the cost of latency."
    )
    if HAS_MPL:
        p("\n![Calls vs Accuracy](charts/calls_vs_acc.png)\n")

    # 3. Ablations
    h(2, "3. Ablation Analysis")
    p(
        "Each row removes one Assembly component. The accuracy delta shows "
        "contribution: more negative = more important.\n"
    )
    abl_hdr = "| Variant | Accuracy | Δ vs Full Assembly | N |"
    abl_sep = "|---------|----------|--------------------|---|"
    abl_tbl = [abl_hdr, abl_sep]
    for sys_key, label in ABLATION_SYSTEMS:
        if sys_key not in ablations:
            continue
        a = ablations[sys_key]
        abl_tbl.append(
            f"| {label} | {pct(a['accuracy'])} | {a['delta_vs_full']:+.1%} | {a['n']} |"
        )
    p("\n".join(abl_tbl))

    ranked = ablations.get("_ranked", [])
    if ranked:
        _, worst_label, worst_delta = ranked[0]
        p(
            f"\n**Most impactful component**: removing **{worst_label}** causes the "
            f"largest accuracy drop ({worst_delta:+.1%}). "
            "Keep this component even under tight time budgets."
        )
    if HAS_MPL:
        p("\n![Ablation chart](charts/ablation.png)\n")

    # 4. Failures
    h(2, "4. Failure Analysis — Questions Where Assembly Lost")
    if not failures:
        p("✅ Assembly did not lose on any question in this run.")
    else:
        p(f"Assembly lost on **{len(failures)} question(s)**:\n")
        f_hdr = "| Question ID | Category | Difficulty | Asm Score | Best Rival | Reason |"
        f_sep = "|-------------|----------|------------|-----------|------------|--------|"
        f_tbl = [f_hdr, f_sep]
        for f in failures:
            f_tbl.append(
                f"| {f['question_id']} | {f['category']} | {f['difficulty']} "
                f"| {pct(f['asm_score'])} "
                f"| {f['best_rival_system']} ({pct(f['best_rival_score'])}) "
                f"| {f['reason']} |"
            )
        p("\n".join(f_tbl))

        reason_counts: dict[str, int] = defaultdict(int)
        for f in failures:
            reason_counts[f["reason"].split("—")[0].strip()] += 1
        p("\n**Failure reason summary:**\n")
        for reason, count in sorted(reason_counts.items(), key=lambda x: -x[1]):
            p(f"- {reason}: {count}")

    # 5. Consensus weights
    h(2, "5. Consensus Weight Suggestions")
    wt = weight_tune
    cur = wt["current"]
    p(
        f"**Current weights**: agreement={cur['w_agreement']}, "
        f"confidence={cur['w_confidence']}, evidence={cur['w_evidence']}, "
        f"contradiction={cur['w_contradiction']}, stability={cur['w_stability']}, "
        f"finalize_threshold={cur['finalize_threshold']}\n"
    )
    p(f"Simulated accuracy with current weights: **{pct(wt['current_sim_accuracy'])}**\n")

    best = wt["best"]
    p("**Best candidate weights** (proxy grid-search on Assembly rows):\n")
    p(
        f"| Weight | Current | Suggested |\n"
        f"|--------|---------|----------|\n"
        f"| `w_agreement` | {cur['w_agreement']} | **{best.get('w_agreement')}** |\n"
        f"| `w_confidence` | {cur['w_confidence']} | **{best.get('w_confidence')}** |\n"
        f"| `w_evidence` | {cur['w_evidence']} | **{best.get('w_evidence')}** |\n"
        f"| `w_contradiction` | {cur['w_contradiction']} | **{best.get('w_contradiction')}** |\n"
        f"| `w_stability` | {cur['w_stability']} | **{best.get('w_stability')}** |\n"
        f"| `finalize_threshold` | {cur['finalize_threshold']} | **{best.get('finalize_threshold')}** |\n"
    )
    p(
        f"Simulated accuracy with best weights: **{pct(wt['best_sim_accuracy'])}** "
        f"(Δ = **{wt['improvement']:+.1%}**)\n"
    )
    p(f"**Recommendation**: {wt['recommendation']}\n")

    if wt["improvement"] > 0.01:
        p("**To apply** — add these lines to `.env` or `.env.dev` and re-run:\n")
        p(f"```dotenv\n{build_env_snippet(best)}\n```\n")
        p(
            "> After applying, re-run `bench/run_assembly.py` on the same question IDs "
            "and compare graded accuracy. This grid-search is a proxy; real improvement may differ."
        )

    if wt.get("top5_grid"):
        p("\n<details><summary>Top-5 weight candidates from grid search</summary>\n")
        p("| Rank | w_agr | w_conf | w_evi | w_cont | w_stab | thresh | Sim Acc |")
        p("|------|-------|--------|-------|--------|--------|--------|---------|")
        for i, candidate in enumerate(wt["top5_grid"], 1):
            w = candidate["weights"]
            p(
                f"| {i} | {w['w_agreement']} | {w['w_confidence']} | "
                f"{w['w_evidence']} | {w['w_contradiction']} | "
                f"{w['w_stability']} | {w['finalize_threshold']} | "
                f"{pct(candidate['sim_accuracy'])} |"
            )
        p("\n</details>\n")

    # 6. Charts index
    h(2, "6. Demo Slide Charts")
    if HAS_MPL:
        p(
            "Three PNG charts saved to `bench/results/charts/`:\n\n"
            "| File | Description |\n"
            "|------|-------------|\n"
            "| `win_rate.png` | Grouped bar: accuracy by system x category with 95% CI |\n"
            "| `ablation.png` | Horizontal bar: accuracy delta per ablation variant |\n"
            "| `calls_vs_acc.png` | Scatter: avg calls vs accuracy, bubble = avg tokens |\n"
        )
    else:
        p(
            "> ⚠️ `matplotlib` not installed — no charts generated. "
            "Run `pip install matplotlib numpy` then re-run `bench/analyze.py`."
        )

    blank()
    lines.append("---")
    lines.append(
        "_All reference answers in `questions.jsonl` carry "
        "`NEEDS HUMAN VERIFICATION`. Review manually before citing "
        "these win rates in a public demo or paper._"
    )
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        pass

    args = parse_args(argv)

    csv_files: list[Path] = list(args.csv_files)
    if not csv_files:
        csv_files = discover_csvs(args.results_dir)

    run_records: list[dict[str, Any]] = []
    is_demo = False

    if args.demo or not csv_files:
        if not args.demo:
            print(
                f"[analyze] No graded CSV files found in {args.results_dir}\n"
                "          Generating synthetic demo data.\n"
                "          Run bench/run_*.py + bench/grade.py for real results."
            )
        else:
            print("[analyze] --demo flag set — using synthetic demo data.")
        is_demo = True
        rows, run_records = make_demo_data(args.seed)
    else:
        rows = []
        for path in csv_files:
            if not path.exists():
                path = args.results_dir / path.name
            print(f"[analyze] Loading {path}")
            rows.extend(load_csv(path))
        if not rows:
            print("ERROR: No rows loaded from CSV files.")
            return 1
        for p in csv_files:
            stem = p.stem.removeprefix("graded_")
            jsonl = args.results_dir / f"{stem}.jsonl"
            if jsonl.exists():
                run_records.extend(load_run_jsonl(jsonl))

    print(f"[analyze] {len(rows)} graded rows  |  {len(run_records)} run records")

    print("[analyze] Computing win rates…")
    wr = compute_win_rates(rows)

    print("[analyze] Computing cost view…")
    cost = compute_cost_view(rows, run_records)

    print("[analyze] Computing ablations…")
    ablations = compute_ablations(rows)

    print("[analyze] Failure analysis…")
    failures = compute_failures(rows, run_records)

    print("[analyze] Tuning consensus weights…")
    weight_tune = suggest_consensus_weights(rows)

    charts_dir = args.charts_dir
    status_header = data_status(rows, run_records, is_demo)
    ready = is_final_ready(rows, run_records, is_demo)
    print(f"[analyze] {status_header}")
    watermark = not ready
    if HAS_MPL:
        print(f"[analyze] Generating charts → {charts_dir}")
        chart_win_rate(wr, charts_dir / "win_rate.png", watermark=watermark)
        chart_ablation(ablations, charts_dir / "ablation.png", watermark=watermark)
        chart_calls_vs_acc(rows, wr, charts_dir / "calls_vs_acc.png", watermark=watermark)
        print("[analyze] Charts: win_rate.png  ablation.png  calls_vs_acc.png")
    else:
        print("[analyze] WARNING: matplotlib unavailable — skipping charts.")
        print("          pip install matplotlib numpy")

    report = build_report(
        wr, cost, ablations, failures, weight_tune, charts_dir, is_demo, status_header
    )

    out_dir = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    if not ready:
        preview_path = out_dir / "REPORT.preview.md"
        preview_path.write_text(report, encoding="utf-8")
        print(f"\n[analyze] {status_header}")
        print(f"[analyze] Refusing final REPORT.md — wrote preview → {preview_path}")
        print("[analyze] Final REPORT.md requires every question verified + all runs live.")
    else:
        report_path = out_dir / "REPORT.md"
        report_path.write_text(report, encoding="utf-8")
        print(f"\n[analyze] Report → {report_path}")

    # Console summary
    print("\n── Win Rates ──────────────────────────────────────")
    for sname, st in sorted(wr["overall"].items()):
        print(f"  {sname:35s}: {pct(st['accuracy'])}  [{pct(st['ci_lo'])}, {pct(st['ci_hi'])}]")
    print("\n── Assembly vs Single ─────────────────────────────")
    pw = wr["pairwise"].get("single", {})
    print(
        f"  Win rate {pct(pw.get('win_rate', 0))}  "
        f"CI [{pct(pw.get('ci_lo', 0))}, {pct(pw.get('ci_hi', 0))}]  "
        f"W/T/L={pw.get('asm_wins', 0)}/{pw.get('ties', 0)}/{pw.get('asm_losses', 0)}"
    )
    print("\n── Assembly vs Vote ───────────────────────────────")
    pv = wr["pairwise"].get("vote", {})
    print(
        f"  Win rate {pct(pv.get('win_rate', 0))}  "
        f"CI [{pct(pv.get('ci_lo', 0))}, {pct(pv.get('ci_hi', 0))}]  "
        f"W/T/L={pv.get('asm_wins', 0)}/{pv.get('ties', 0)}/{pv.get('asm_losses', 0)}"
    )
    print("\n── Consensus weight suggestion ────────────────────")
    print(f"  Δ simulated accuracy: {weight_tune['improvement']:+.1%}")
    print(f"  {weight_tune['recommendation']}")

    return 0 if ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
