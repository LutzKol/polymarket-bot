"""
Fetch REAL historical Chainlink BTC/USD data from Polygon RPC
Optimized with binary search and sampling
"""

import csv
import time
from datetime import datetime, timezone, timedelta
from web3 import Web3

GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
RESET = "\033[0m"
BOLD = "\033[1m"

# Polygon RPC (working)
RPC_URL = "https://polygon-bor-rpc.publicnode.com"

# Chainlink BTC/USD on Polygon
CHAINLINK_BTC_USD = "0xc907E116054Ad103354f2D350FD2514433D57F6f"

# ABI
ABI = [
    {"inputs": [], "name": "latestRoundData", "outputs": [
        {"name": "roundId", "type": "uint80"},
        {"name": "answer", "type": "int256"},
        {"name": "startedAt", "type": "uint256"},
        {"name": "updatedAt", "type": "uint256"},
        {"name": "answeredInRound", "type": "uint80"}
    ], "stateMutability": "view", "type": "function"},
    {"inputs": [{"name": "_roundId", "type": "uint80"}], "name": "getRoundData", "outputs": [
        {"name": "roundId", "type": "uint80"},
        {"name": "answer", "type": "int256"},
        {"name": "startedAt", "type": "uint256"},
        {"name": "updatedAt", "type": "uint256"},
        {"name": "answeredInRound", "type": "uint80"}
    ], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "decimals", "outputs": [{"name": "", "type": "uint8"}], "stateMutability": "view", "type": "function"}
]


def fetch_chainlink_data(days: int = 30, max_samples: int = 5000):
    """
    Fetch real Chainlink BTC/USD data from Polygon.
    Uses binary search + sampling for efficiency.
    """

    print(f"\n{BOLD}=== Fetching REAL Chainlink BTC/USD Data ==={RESET}\n")

    # Connect
    w3 = Web3(Web3.HTTPProvider(RPC_URL, request_kwargs={'timeout': 30}))
    if not w3.is_connected():
        print(f"{RED}[ERROR]{RESET} Cannot connect to Polygon RPC")
        return []

    print(f"{GREEN}[OK]{RESET} Connected to Polygon")

    # Contract
    contract = w3.eth.contract(
        address=Web3.to_checksum_address(CHAINLINK_BTC_USD),
        abi=ABI
    )

    decimals = contract.functions.decimals().call()
    print(f"Decimals: {decimals}")

    # Get latest round
    latest = contract.functions.latestRoundData().call()
    phase_id = latest[0] >> 64
    latest_agg = latest[0] & 0xFFFFFFFFFFFFFFFF
    latest_price = latest[1] / (10 ** decimals)
    latest_ts = latest[3]

    print(f"Latest price: ${latest_price:,.2f}")
    print(f"Latest time: {datetime.fromtimestamp(latest_ts, tz=timezone.utc)}")
    print(f"Phase: {phase_id}, Agg round: {latest_agg}")

    # Cutoff
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    cutoff_ts = int(cutoff.timestamp())
    print(f"Cutoff: {cutoff}")

    # Binary search for start round
    print("\nBinary search for start round...")
    low, high = max(1, latest_agg - 200000), latest_agg

    while high - low > 10:
        mid = (low + high) // 2
        try:
            data = contract.functions.getRoundData((phase_id << 64) | mid).call()
            if data[3] < cutoff_ts:
                low = mid + 1
            else:
                high = mid
        except:
            low = mid + 1

    start_round = low
    total_rounds = latest_agg - start_round
    print(f"Start round: {start_round}")
    print(f"Total rounds: {total_rounds}")

    # Calculate sample rate
    sample_rate = max(1, total_rounds // max_samples)
    expected_samples = total_rounds // sample_rate
    print(f"Sample rate: every {sample_rate} rounds (~{expected_samples} samples)")

    # Fetch data
    all_data = []
    start_time = time.time()
    last_progress = 0

    for i, r in enumerate(range(start_round, latest_agg + 1, sample_rate)):
        try:
            data = contract.functions.getRoundData((phase_id << 64) | r).call()
            price = data[1] / (10 ** decimals)
            ts = data[3]

            if ts >= cutoff_ts and price > 0:
                all_data.append({
                    "roundId": data[0],
                    "timestamp": ts,
                    "price": price
                })

        except Exception:
            pass

        # Progress
        progress = (i * sample_rate) / total_rounds * 100
        if progress - last_progress >= 10:
            elapsed = time.time() - start_time
            print(f"  {progress:.0f}% - {len(all_data)} samples ({elapsed:.0f}s)")
            last_progress = progress

        time.sleep(0.01)  # Rate limit

    elapsed = time.time() - start_time
    print(f"\n{GREEN}[SUCCESS]{RESET} Fetched {len(all_data)} real data points in {elapsed:.0f}s")

    # Sort
    all_data.sort(key=lambda x: x["timestamp"])

    return all_data


def save_to_csv(data: list, filename: str = "chainlink_history.csv"):
    """Save to CSV"""
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["roundId", "timestamp", "price"])
        writer.writeheader()
        writer.writerows(data)
    print(f"{GREEN}[SAVED]{RESET} {filename} ({len(data)} rows)")


def print_stats(data: list):
    """Print statistics"""
    if not data:
        return

    oldest = datetime.fromtimestamp(data[0]["timestamp"], tz=timezone.utc)
    newest = datetime.fromtimestamp(data[-1]["timestamp"], tz=timezone.utc)
    days = (newest - oldest).total_seconds() / 86400

    prices = [d["price"] for d in data]

    print(f"\n{BOLD}=== Data Statistics ==={RESET}")
    print(f"Date range: {oldest.strftime('%Y-%m-%d %H:%M')} to {newest.strftime('%Y-%m-%d %H:%M')}")
    print(f"Days covered: {days:.1f}")
    print(f"Total samples: {len(data)}")
    print(f"Samples/day: {len(data) / max(days, 1):.1f}")
    print(f"Price range: ${min(prices):,.2f} - ${max(prices):,.2f}")

    # Intervals
    intervals = []
    for i in range(1, len(data)):
        interval = data[i]["timestamp"] - data[i - 1]["timestamp"]
        if interval > 0:
            intervals.append(interval)

    if intervals:
        print(f"Avg interval: {sum(intervals)/len(intervals):.0f}s")


if __name__ == "__main__":
    try:
        data = fetch_chainlink_data(days=30, max_samples=5000)

        if data:
            save_to_csv(data)
            print_stats(data)
        else:
            print(f"{RED}[ERROR]{RESET} No data fetched")

    except Exception as e:
        print(f"{RED}[ERROR]{RESET} {e}")
        import traceback
        traceback.print_exc()
