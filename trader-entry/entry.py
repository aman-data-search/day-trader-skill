"""
Opening Range Breakout (ORB) Detection Module for US100 M5.
Evaluates the 09:30-09:45 ET range and identifies completed breakout candle closes.
"""

from datetime import datetime
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

EASTERN_TZ = ZoneInfo("America/New_York")


def find_project_root() -> Path:
    """Finds project root directory by inspecting parent markers."""
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / ".env").exists() or (current / "trader").exists():
            return current
        current = current.parent
    return Path(__file__).resolve().parent.parent


def load_config(root_dir: Path) -> dict:
    cfg_path = root_dir / "trader" / "config.json"
    if not cfg_path.exists():
        raise FileNotFoundError(f"Configuration missing: {cfg_path}")
    with open(cfg_path, "r", encoding="utf-8") as f:
        return json.load(f)


def evaluate_orb(bars: list[dict], config: dict) -> dict:
    """
    Evaluates completed M5 session bars for Opening Range structure and breakouts.
    """
    orb_count = config["strategy"]["orb_candle_count"]  # 3 candles (09:30-09:45 ET)
    timeframe = config["strategy"]["timeframe"]
    symbol = config["symbol"]["display_name"]
    proxy = config["symbol"]["proxy"]

    if len(bars) < orb_count:
        return {
            "status": "WAITING_FOR_ORB",
            "message": f"Forming opening range: {len(bars)}/{orb_count} bars completed.",
            "orb_completed": False,
            "bars_count": len(bars),
        }

    orb_bars = bars[:orb_count]
    orb_high = max(b["high"] for b in orb_bars)
    orb_low = min(b["low"] for b in orb_bars)
    orb_midpoint = round((orb_high + orb_low) / 2.0, 4)

    result = {
        "symbol": symbol,
        "proxy": proxy,
        "timeframe": timeframe,
        "orb_completed": True,
        "orb_high": orb_high,
        "orb_low": orb_low,
        "orb_midpoint": orb_midpoint,
        "range_points": round(orb_high - orb_low, 4),
        "total_session_bars": len(bars),
        "status": "INSIDE_RANGE",
        "signal": None,
    }

    if len(bars) == orb_count:
        result["message"] = "Opening range locked (09:30-09:45 ET). Awaiting breakout close."
        return result

    # Inspect post-ORB candles for confirmed breakout close
    post_orb_bars = bars[orb_count:]
    for idx, bar in enumerate(post_orb_bars):
        close_price = bar["close"]
        bar_time = bar["timestamp"]

        if close_price > orb_high:
            result.update({
                "status": "SIGNAL",
                "signal": {
                    "direction": "BUY",
                    "action": "Bullish Range Expansion",
                    "trigger_timestamp": bar_time,
                    "trigger_candle_index": orb_count + idx,
                    "entry_price": close_price,
                    "sl_reference": orb_midpoint,
                    "orb_high": orb_high,
                    "orb_low": orb_low,
                },
                "message": f"Bullish breakout confirmed at {bar_time} with close above ORB High.",
            })
            return result

        if close_price < orb_low:
            result.update({
                "status": "SIGNAL",
                "signal": {
                    "direction": "SELL",
                    "action": "Bearish Range Expansion",
                    "trigger_timestamp": bar_time,
                    "trigger_candle_index": orb_count + idx,
                    "entry_price": close_price,
                    "sl_reference": orb_midpoint,
                    "orb_high": orb_high,
                    "orb_low": orb_low,
                },
                "message": f"Bearish breakout confirmed at {bar_time} with close below ORB Low.",
            })
            return result

    latest_bar = bars[-1]
    result["message"] = f"Price inside range as of {latest_bar['timestamp']} (Close: {latest_bar['close']})."
    return result


def run_entry(bars_override: list[dict] | None = None) -> dict:
    """Entry point execution. Writes state to trader/state/entry.json."""
    root_dir = find_project_root()
    sys.path.insert(0, str(root_dir))

    from trader.feed import get_today_session_bars

    config = load_config(root_dir)

    if bars_override is not None:
        bars = bars_override
    else:
        bars = get_today_session_bars(root_dir)

    evaluation = evaluate_orb(bars, config)

    state_path = root_dir / "trader" / "state" / "entry.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(evaluation, f, indent=2)

    return evaluation


if __name__ == "__main__":
    result = run_entry()
    print(f"[*] ORB Entry Evaluation: {result.get('status')} - {result.get('message')}")