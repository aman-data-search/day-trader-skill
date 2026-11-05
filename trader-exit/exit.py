"""
Exit & Risk Geometry Module for US100 M5.
Calculates midpoint stop-loss, strict 1.5R take-profit, and session cut-off rules.
"""

import json
from pathlib import Path
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
        raise FileNotFoundError(f"Required artifact not found: {file_path}")
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def calculate_trade_plan(entry_data: dict, config: dict) -> dict:
    """
    Computes strict midpoint SL and 1.5R TP targets based on the entry state.
    """
    if entry_data.get("status") != "SIGNAL" or not entry_data.get("signal"):
        return {
            "status": "NO_SIGNAL",
            "message": "No active breakout signal detected. Plan generation skipped.",
            "plan": None,
        }

    signal = entry_data["signal"]
    direction = signal["direction"]
    entry_price = float(signal["entry_price"])
    sl_price = float(signal["sl_reference"])
    r_multiple = float(config["strategy"].get("r_multiple", 1.5))
    hard_flat_et = config["strategy"].get("hard_flat_et", "15:55")

    # Risk distance R
    risk_r = round(abs(entry_price - sl_price), 4)
    if risk_r <= 0.0:
        raise ValueError(f"Invalid risk distance: {risk_r}. Entry price matches stop-loss price.")

    reward_dist = round(risk_r * r_multiple, 4)

    if direction == "BUY":
        tp_price = round(entry_price + reward_dist, 4)
    elif direction == "SELL":
        tp_price = round(entry_price - reward_dist, 4)
    else:
        raise ValueError(f"Unknown signal direction: {direction}")

    plan = {
        "status": "PLAN_READY",
        "symbol": entry_data.get("symbol", "US100 / NAS100"),
        "proxy": entry_data.get("proxy", "QQQ"),
        "direction": direction,
        "trigger_timestamp": signal.get("trigger_timestamp"),
        "entry_price": entry_price,
        "stop_loss": sl_price,
        "take_profit": tp_price,
        "risk_points": risk_r,
        "reward_points": reward_dist,
        "r_multiple": r_multiple,
        "orb_high": signal.get("orb_high"),
        "orb_low": signal.get("orb_low"),
        "hard_flat_et": hard_flat_et,
    }

    return plan


def run_exit(entry_override: dict | None = None) -> dict:
    """Entry point execution. Writes verified trade plan to trader/state/plan.json."""
    root_dir = find_project_root()
    config = load_json(root_dir / "trader" / "config.json")

    if entry_override is not None:
        entry_data = entry_override
    else:
        entry_path = root_dir / "trader" / "state" / "entry.json"
        entry_data = load_json(entry_path)

    plan_result = calculate_trade_plan(entry_data, config)

    state_path = root_dir / "trader" / "state" / "plan.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(plan_result, f, indent=2)

    return plan_result


if __name__ == "__main__":
    result = run_exit()
    if result.get("status") == "PLAN_READY":
        p = result
        print(f"[*] Trade Plan Ready [{p['direction']}]: Entry={p['entry_price']} | SL={p['stop_loss']} | TP={p['take_profit']} (1.5R: {p['reward_points']} pts)")
    else:
        print(f"[*] Trade Plan Status: {result.get('status')} - {result.get('message')}")