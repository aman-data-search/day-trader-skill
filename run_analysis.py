"""
Master CLI Runner & Terminal Trade Card Generator for US100 M5 ORB.
Orchestrates cache synchronization and active breakout scanning.
"""

import argparse
from datetime import datetime
import importlib.util
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

EASTERN_TZ = ZoneInfo("America/New_York")


def find_project_root() -> Path:
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / ".env").exists() or (current / "trader").exists():
            return current
        current = current.parent
    return Path(__file__).resolve().parent


def load_module_from_path(module_name: str, file_path: Path):
    """Dynamically loads Python module from filesystem path to support hyphenated directories."""
    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load module specification from: {file_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def format_trade_card(entry: dict, plan: dict, sim: dict) -> str:
    """Formats terminal trade card according to design specifications."""
    sig = entry.get("signal", {})
    trigger_ts = sig.get("trigger_timestamp", datetime.now(EASTERN_TZ).strftime("%Y-%m-%d %H:%M:%S"))
    direction = plan.get("direction", "UNKNOWN")
    action_text = "Bullish Range Expansion" if direction == "BUY" else "Bearish Range Expansion"
    asset_ref = f"{plan.get('symbol', 'US100 / NAS100')} (Proxy: {plan.get('proxy', 'QQQ')})"

    entry_px = f"{plan.get('entry_price', 0.0):,.2f}"
    sl_px = f"{plan.get('stop_loss', 0.0):,.2f}"
    tp_px = f"{plan.get('take_profit', 0.0):,.2f}"
    risk_pts = f"{plan.get('risk_points', 0.0):,.2f} Index Points"
    reward_pts = f"{plan.get('reward_points', 0.0):,.2f} Index Points"

    p_target = sim.get("target_probability_pct", 0.0)
    p_stop = sim.get("stop_probability_pct", 0.0)
    ev_r = sim.get("expected_return_r", 0.0)
    iterations = sim.get("iterations", 10000)

    card = f"""
======================================================================
               US100 INTRADAY DECISION CARD (M5 ORB)                 
======================================================================
  Signal Timestamp    : {trigger_ts} ET
  Direction           : {direction} ({action_text})
  Asset Reference     : {asset_ref}
----------------------------------------------------------------------
  TRADE EXECUTION TARGETS
  Entry Reference     : {entry_px}
  Stop-Loss Level     : {sl_px}  [Strict ORB Midpoint]
  Take-Profit Level   : {tp_px}  [Strict 1.5R Target]
  Risk Distance       : {risk_pts}
  Reward Distance     : {reward_pts}
----------------------------------------------------------------------
  MONTE CARLO EMPIRICAL AUDIT ({iterations:,} Bootstrap Runs | 60-Day RTH)
  Target Probability  : {p_target}% (Hits 1.5R before Midpoint SL)
  Stop Probability    : {p_stop}%
  Expected Return     : {ev_r:+} R per trade
======================================================================
  Execution Note      : Place order manually on MT5.
  Session Cut-Off     : Close trade manually by {plan.get('hard_flat_et', '15:55')} ET if still active.
======================================================================
"""
    return card.strip()


def execute_scan(root_dir: Path) -> None:
    """Executes the entry -> exit -> timemachine analysis pipeline."""
    entry_script = root_dir / "trader-entry" / "entry.py"
    exit_script = root_dir / "trader-exit" / "exit.py"
    tm_script = root_dir / "trader-timemachine" / "timemachine.py"

    entry_mod = load_module_from_path("custom_entry_mod", entry_script)
    exit_mod = load_module_from_path("custom_exit_mod", exit_script)
    tm_mod = load_module_from_path("custom_tm_mod", tm_script)

    print("[*] Polling completed M5 bars and evaluating Opening Range...")
    entry_state = entry_mod.run_entry()

    if entry_state.get("status") == "WAITING_FOR_ORB":
        print(f"[!] {entry_state.get('message')}")
        return

    if entry_state.get("status") == "INSIDE_RANGE":
        print(f"[-] Status: INSIDE_RANGE | {entry_state.get('message')}")
        return

    if entry_state.get("status") == "SIGNAL":
        print("[+] Signal detected. Calculating geometric parameters...")
        plan_state = exit_mod.run_exit()

        print("[*] Running 10,000-path Monte Carlo bootstrap verification...")
        sim_state = tm_mod.run_timemachine()

        card = format_trade_card(entry_state, plan_state, sim_state)
        print("\n" + card + "\n")
    else:
        print(f"[?] Status: {entry_state.get('status')} - {entry_state.get('message')}")


def main() -> None:
    parser = argparse.ArgumentParser(description="US100 M5 Decision Support CLI")
    parser.add_argument("--cache", action="store_true", help="Sync 60-day RTH historical bars from Alpaca")
    parser.add_argument("--scan", action="store_true", help="Execute active M5 ORB evaluation pipeline")

    args = parser.parse_args()
    root_dir = find_project_root()
    sys.path.insert(0, str(root_dir))

    if args.cache:
        from trader.feed import sync_historical_cache
        print("[*] Refreshing 60-day RTH historical cache...")
        count = sync_historical_cache(root_dir)
        print(f"[+] Successfully cached {count} bars.")
    elif args.scan:
        execute_scan(root_dir)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()