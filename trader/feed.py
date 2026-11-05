"""
Data Ingestion Layer for Alpaca Market Data v2.
Fetches RTH 5-minute bars for proxy tickers (QQQ) using standard library HTTP tools.
"""

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request
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


def load_credentials(root_dir: Path | None = None) -> tuple[str, str]:
    """
    Parses .env file directly without external dependencies.
    Raises RuntimeError if keys are missing.
    """
    if root_dir is None:
        root_dir = find_project_root()

    env_path = root_dir / ".env"
    api_key = os.environ.get("ALPACA_API_KEY")
    secret_key = os.environ.get("ALPACA_SECRET_KEY")

    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("'\"")
                    if k == "ALPACA_API_KEY" and not api_key:
                        api_key = v
                    elif k == "ALPACA_SECRET_KEY" and not secret_key:
                        secret_key = v

    if not api_key or not secret_key:
        raise RuntimeError(
            "Alpaca API credentials missing. Ensure ALPACA_API_KEY and "
            "ALPACA_SECRET_KEY are defined in .env or environment variables."
        )

    return api_key, secret_key


def load_config(root_dir: Path | None = None) -> dict:
    """Loads runtime configuration settings from trader/config.json."""
    if root_dir is None:
        root_dir = find_project_root()
    cfg_path = root_dir / "trader" / "config.json"
    if not cfg_path.exists():
        raise FileNotFoundError(f"Configuration file not found at: {cfg_path}")
    with open(cfg_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _http_get_json(url: str, headers: dict) -> dict:
    """Executes an authenticated HTTP GET request and returns JSON."""
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status != 200:
                raise RuntimeError(f"HTTP request failed with status {resp.status}")
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Alpaca API HTTP {e.code}: {error_body}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Network connection failed: {e.reason}") from e


def is_rth(dt_eastern: datetime) -> bool:
    """Determines if an Eastern Time datetime falls strictly within Regular Trading Hours (09:30 - 16:00 ET)."""
    t = dt_eastern.time()
    market_open = datetime.strptime("09:30", "%H:%M").time()
    market_close = datetime.strptime("16:00", "%H:%M").time()
    return market_open <= t < market_close


def parse_rfc3339(ts_str: str) -> datetime:
    """Parses RFC3339 timestamp and converts to Eastern Time."""
    if ts_str.endswith("Z"):
        ts_str = ts_str[:-1] + "+00:00"
    dt = datetime.fromisoformat(ts_str)
    return dt.astimezone(EASTERN_TZ)


def fetch_bars(
    symbol: str,
    start_dt: datetime,
    end_dt: datetime,
    api_key: str,
    secret_key: str,
    feed: str = "iex",
    timeframe: str = "5Min",
) -> list[dict]:
    """
    Fetches historical bars from Alpaca Data API v2 with automatic pagination.
    Normalizes timestamps to Eastern Time and filters to RTH.
    """
    base_url = f"https://data.alpaca.markets/v2/stocks/{symbol}/bars"
    headers = {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": secret_key,
        "Accept": "application/json",
    }

    start_iso = start_dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    end_iso = end_dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    collected_bars = []
    page_token = None

    while True:
        params = {
            "timeframe": timeframe,
            "start": start_iso,
            "end": end_iso,
            "limit": 10000,
            "feed": feed,
            "sort": "asc",
        }
        if page_token:
            params["page_token"] = page_token

        query_str = urllib.parse.urlencode(params)
        full_url = f"{base_url}?{query_str}"
        payload = _http_get_json(full_url, headers)

        raw_bars = payload.get("bars", [])
        if not raw_bars:
            break

        for b in raw_bars:
            t_eastern = parse_rfc3339(b["t"])
            if is_rth(t_eastern):
                collected_bars.append({
                    "timestamp": t_eastern.strftime("%Y-%m-%d %H:%M:%S"),
                    "epoch": int(t_eastern.timestamp()),
                    "open": float(b["o"]),
                    "high": float(b["h"]),
                    "low": float(b["l"]),
                    "close": float(b["c"]),
                    "volume": int(b["v"]),
                })

        page_token = payload.get("next_page_token")
        if not page_token:
            break

    return collected_bars


def sync_historical_cache(root_dir: Path | None = None) -> int:
    """
    Pulls 60 days of historical RTH M5 bars and stores them in trader/data/history_m5.json.
    Returns the total count of cached bars.
    """
    if root_dir is None:
        root_dir = find_project_root()

    config = load_config(root_dir)
    api_key, secret_key = load_credentials(root_dir)

    symbol = config["symbol"]["proxy"]
    lookback = config["historical_data"]["lookback_days"]
    feed = config["historical_data"]["feed"]
    timeframe = config["strategy"]["timeframe"]

    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=lookback)

    bars = fetch_bars(
        symbol=symbol,
        start_dt=start_time,
        end_dt=end_time,
        api_key=api_key,
        secret_key=secret_key,
        feed=feed,
        timeframe=timeframe,
    )

    out_path = root_dir / config["historical_data"]["cache_path"]
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "symbol": symbol,
                "timeframe": timeframe,
                "feed": feed,
                "updated_at": datetime.now(EASTERN_TZ).strftime("%Y-%m-%d %H:%M:%S"),
                "bar_count": len(bars),
                "bars": bars,
            },
            f,
            indent=2,
        )

    return len(bars)


def get_today_session_bars(root_dir: Path | None = None) -> list[dict]:
    """
    Fetches all completed M5 bars for today's active RTH session.
    """
    if root_dir is None:
        root_dir = find_project_root()

    config = load_config(root_dir)
    api_key, secret_key = load_credentials(root_dir)

    symbol = config["symbol"]["proxy"]
    feed = config["historical_data"]["feed"]
    timeframe = config["strategy"]["timeframe"]

    now_et = datetime.now(EASTERN_TZ)
    session_start_et = now_et.replace(hour=9, minute=30, second=0, microsecond=0)

    if now_et < session_start_et:
        return []

    bars = fetch_bars(
        symbol=symbol,
        start_dt=session_start_et,
        end_dt=now_et,
        api_key=api_key,
        secret_key=secret_key,
        feed=feed,
        timeframe=timeframe,
    )

    return bars


if __name__ == "__main__":
    try:
        print("[*] Initiating 60-day historical cache sync from Alpaca...")
        total = sync_historical_cache()
        print(f"[+] Successfully cached {total} RTH M5 bars to trader/data/history_m5.json")
    except Exception as exc:
        print(f"[-] Data Ingestion Error: {exc}", file=sys.stderr)
        sys.exit(1)