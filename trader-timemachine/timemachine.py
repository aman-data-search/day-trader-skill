"""
Monte Carlo Empirical Audit Engine for US100 M5.
Executes 10,000 bootstrap simulations using 60-day RTH historical 5-minute returns.
"""

from datetime import datetime
import json
from pathlib import Path
import random
import sys


def find_project_root() -> Path:
    """Finds project root directory by inspecting parent markers."""
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / ".env").exists() or (current / "trader").exists():
            return current
        current = current.parent
    return Path(__file__).resolve().parent.parent


def load_json(file_path: Path) -> dict:
    if not file_path.exists():
        raise FileNotFoundError(f"Required file not found: {file_path}")
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_empirical_delta_distribution(bars: list[dict]) -> list[float]:
    """
    Extracts delta points (close - open) for each completed M5 bar.
    """
    deltas = []
    for b in bars:
        delta = round(float(b["close"]) - float(b["open"]), 4)
        deltas.append(delta)
    if not deltas:
        raise ValueError("Historical bars empty. Run trader/feed.py to populate cache.")
    return deltas


def run_monte_carlo(
    plan: dict,
    historical_bars: list[dict],
    iterations: int = 10000,
    horizon_bars: int = 30,
    seed: int = 42,
) -> dict:
    """
    Replays 10,000 forward paths to calculate target vs stop empirical probabilities.
    """
    direction = plan["direction"]
    entry_price = float(plan["entry_price"])
    stop_loss = float(plan["stop_loss"])
    take_profit = float(plan["take_profit"])

    deltas = build_empirical_delta_distribution(historical_bars)
    rng = random.Random(seed)

    target_hits = 0
    stop_hits = 0
    undecided = 0

    for _ in range(iterations):
        current_price = entry_price
        resolved = False

        for _ in range(horizon_bars):
            step = rng.choice(deltas)
            current_price += step

            if direction == "BUY":
                if current_price >= take_profit:
                    target_hits += 1
                    resolved = True
                    break
                if current_price <= stop_loss:
                    stop_hits += 1
                    resolved = True
                    break
            elif direction == "SELL":
                if current_price <= take_profit:
                    target_hits += 1
                    resolved = True
                    break
                if current_price >= stop_loss:
                    stop_hits += 1
                    resolved = True
                    break

        if not resolved:
            undecided += 1

    p_target = round((target_hits / iterations) * 100.0, 2)
    p_stop = round((stop_hits / iterations) * 100.0, 2)
    p_undecided = round((undecided / iterations) * 100.0, 2)

    # Expected value in terms of R (1.5 for win, -1.0 for loss)
    ev_r = round(((p_target / 100.0) * 1.5) - ((p_stop / 100.0) * 1.0), 3)

    return {
        "status": "SIMULATION_COMPLETE",
        "iterations": iterations,
        "horizon_bars": horizon_bars,
        "historical_sample_size": len(historical_bars),
        "target_probability_pct": p_target,
        "stop_probability_pct": p_stop,
        "undecided_probability_pct": p_undecided,
        "expected_return_r": ev_r,
        "target_hit_count": target_hits,
        "stop_hit_count": stop_hits,
        "undecided_count": undecided,
    }


def run_timemachine(
    plan_override: dict | None = None,
    history_override: list[dict] | None = None,
) -> dict:
    """Entry point execution. Writes simulation metrics to trader/state/simulation.json."""
    root_dir = find_project_root()
    config = load_json(root_dir / "trader" / "config.json")

    if plan_override is not None:
        plan = plan_override
    else:
        plan = load_json(root_dir / "trader" / "state" / "plan.json")

    if plan.get("status") != "PLAN_READY":
        skipped = {
            "status": "SKIPPED",
            "message": "Valid trade plan not present. Monte Carlo skipped.",
        }
        return skipped

    if history_override is not None:
        history_bars = history_override
    else:
        hist_cache = load_json(root_dir / config["historical_data"]["cache_path"])
        history_bars = hist_cache.get("bars", [])

    sim_cfg = config.get("simulation", {})
    iterations = int(sim_cfg.get("monte_carlo_iterations", 10000))
    forward_bars = int(sim_cfg.get("forward_bars", 30))

    sim_result = run_monte_carlo(
        plan=plan,
        historical_bars=history_bars,
        iterations=iterations,
        horizon_bars=forward_bars,
    )

    state_path = root_dir / "trader" / "state" / "simulation.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(sim_result, f, indent=2)

    return sim_result


if __name__ == "__main__":
    result = run_timemachine()
    if result.get("status") == "SIMULATION_COMPLETE":
        print(
            f"[*] Monte Carlo Complete (10,000 runs): "
            f"TP={result['target_probability_pct']}% | "
            f"SL={result['stop_probability_pct']}% | "
            f"Undecided={result['undecided_probability_pct']}% | "
            f"EV={result['expected_return_r']:+}R"
        )
    else:
        print(f"[*] Simulation Status: {result.get('status')} - {result.get('message')}")