"""
Slippage Analysis from CLOB Orderbook Data

Calculates slippage for various order sizes using live Polymarket orderbook data.
"""

import os
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
import httpx

# Load credentials from polymarket-bot directory
ENV_PATH = r"C:\Users\kolle\polymarket-bot\.env"
load_dotenv(ENV_PATH)

API_KEY = os.getenv("POLYMARKET_API_KEY")
API_SECRET = os.getenv("POLYMARKET_SECRET")
API_PASSPHRASE = os.getenv("POLYMARKET_PASSPHRASE")

# API URLs
CLOB_BASE_URL = "https://clob.polymarket.com"
GAMMA_API_URL = "https://gamma-api.polymarket.com"

# Order sizes to analyze (in USD)
ORDER_SIZES = [10, 25, 50]

# ANSI colors
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RESET = "\033[0m"
BOLD = "\033[1m"


def load_credentials():
    """Load and verify credentials from .env."""
    if not all([API_KEY, API_SECRET, API_PASSPHRASE]):
        print(f"{RED}[ERROR]{RESET} Missing credentials in {ENV_PATH}")
        print(f"{YELLOW}[INFO]{RESET} Required: POLYMARKET_API_KEY, POLYMARKET_SECRET, POLYMARKET_PASSPHRASE")
        return None

    try:
        from py_clob_client.client import ClobClient
        from py_clob_client.clob_types import ApiCreds

        creds = ApiCreds(
            api_key=API_KEY,
            api_secret=API_SECRET,
            api_passphrase=API_PASSPHRASE
        )

        client = ClobClient(
            host=CLOB_BASE_URL,
            chain_id=137,
            creds=creds
        )

        return client
    except ImportError as e:
        print(f"{RED}[ERROR]{RESET} Missing dependency: {e}")
        print(f"{YELLOW}[INFO]{RESET} Install with: pip install py-clob-client python-dotenv")
        return None


def fetch_orderbook(client, token_id: str) -> dict:
    """Fetch orderbook data for a given token ID."""
    try:
        orderbook = client.get_order_book(str(token_id))
        # Convert OrderBookSummary object to dict
        return {
            "asks": [{"price": o.price, "size": o.size} for o in orderbook.asks] if orderbook.asks else [],
            "bids": [{"price": o.price, "size": o.size} for o in orderbook.bids] if orderbook.bids else []
        }
    except Exception as e:
        print(f"{RED}[ERROR]{RESET} Failed to fetch orderbook: {e}")
        return None


def calculate_fill_price(asks: list, order_size_usd: float) -> tuple[float, float]:
    """
    Calculate the average fill price for a given order size.

    Returns: (fill_price, total_contracts)
    """
    if not asks:
        return None, 0

    remaining_usd = order_size_usd
    total_cost = 0.0
    total_contracts = 0.0

    for ask in asks:
        price = float(ask.get("price", 0))
        size = float(ask.get("size", 0))

        if price <= 0 or size <= 0:
            continue

        # How many contracts can we buy at this price level?
        max_contracts_at_level = remaining_usd / price
        contracts_at_level = min(max_contracts_at_level, size)

        cost_at_level = contracts_at_level * price
        total_cost += cost_at_level
        total_contracts += contracts_at_level
        remaining_usd -= cost_at_level

        if remaining_usd <= 0.001:  # Small epsilon for floating point
            break

    if total_contracts == 0:
        return None, 0

    fill_price = total_cost / total_contracts
    return fill_price, total_contracts


def calculate_slippage(fill_price: float, best_ask: float) -> float:
    """Calculate slippage as percentage."""
    if best_ask <= 0 or fill_price is None:
        return None
    return ((fill_price - best_ask) / best_ask) * 100


def get_next_5min_boundaries(count: int = 6) -> list[int]:
    """Calculate upcoming 5-minute boundary timestamps."""
    now = datetime.now(timezone.utc)
    minutes = now.minute
    next_5min = (minutes // 5 + 1) * 5

    if next_5min >= 60:
        next_boundary = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    else:
        next_boundary = now.replace(minute=next_5min, second=0, microsecond=0)

    timestamps = []
    for i in range(count):
        timestamps.append(int(next_boundary.timestamp()))
        next_boundary += timedelta(minutes=5)

    return timestamps


def find_btc_markets(count: int = 6) -> list[dict]:
    """Find active BTC 5-minute Up/Down markets."""
    timestamps = get_next_5min_boundaries(count)
    found_markets = []

    for ts in timestamps:
        slug = f"btc-updown-5m-{ts}"
        try:
            resp = httpx.get(
                f"{GAMMA_API_URL}/events",
                params={"slug": slug},
                timeout=15
            )
            if resp.status_code == 200:
                events = resp.json()
                for event in events:
                    # Get full event details
                    event_id = event.get("id")
                    try:
                        detail_resp = httpx.get(f"{GAMMA_API_URL}/events/{event_id}", timeout=15)
                        if detail_resp.status_code == 200:
                            full_event = detail_resp.json()
                            markets = full_event.get("markets", [])
                            for market in markets:
                                tokens = market.get("clobTokenIds", [])
                                if isinstance(tokens, str):
                                    import json
                                    tokens = json.loads(tokens)
                                outcomes = market.get("outcomes", ["Up", "Down"])
                                if isinstance(outcomes, str):
                                    import json
                                    outcomes = json.loads(outcomes)

                                found_markets.append({
                                    "slug": slug,
                                    "token_ids": tokens,
                                    "outcomes": outcomes,
                                    "timestamp": ts
                                })
                    except:
                        pass
        except Exception as e:
            pass

    return found_markets


def analyze_markets():
    """Main function: Analyze slippage across multiple markets."""
    print(f"\n{BOLD}=== Slippage Analysis ==={RESET}\n")

    # Load credentials and initialize client
    client = load_credentials()
    if not client:
        return

    print(f"{GREEN}[OK]{RESET} Connected to Polymarket CLOB API")
    print(f"{YELLOW}[INFO]{RESET} Searching for BTC 5-min markets...\n")

    # Find markets - search more to find ones with reasonable prices
    markets = find_btc_markets(count=20)

    if not markets:
        print(f"{RED}[ERROR]{RESET} No BTC 5-min markets found")
        return

    print(f"{GREEN}[OK]{RESET} Found {len(markets)} markets\n")

    # Collect slippage data
    all_slippages = {size: [] for size in ORDER_SIZES}
    analyzed_count = 0

    for market in markets[:5]:  # Analyze up to 5 markets
        slug = market["slug"]
        token_ids = market["token_ids"]
        outcomes = market["outcomes"]

        if not token_ids or len(token_ids) < 2:
            continue

        # Analyze both outcomes to find one with reasonable price (0.30-0.70)
        for i in range(2):
            token_id = token_ids[i]
            outcome = outcomes[i] if i < len(outcomes) else f"Outcome {i}"

            orderbook = fetch_orderbook(client, token_id)
            if not orderbook:
                continue

            asks = orderbook.get("asks", [])
            bids = orderbook.get("bids", [])

            if not asks:
                continue

            best_ask = float(asks[0].get("price", 0))
            best_bid = float(bids[0].get("price", 0)) if bids else 0

            # Note extreme prices but don't skip them
            if best_ask < 0.10 or best_ask > 0.90:
                price_note = " (extreme)"
            else:
                price_note = ""

            spread = best_ask - best_bid if best_bid > 0 else 0
            spread_pct = (spread / best_ask * 100) if best_ask > 0 else 0

            print(f"{BOLD}Market:{RESET} {slug} ({outcome}){price_note}")
            print(f"  Best Ask: {best_ask:.3f}")
            print(f"  Spread: {spread:.3f} ({spread_pct:.1f}%)")

            # Show orderbook depth
            total_ask_depth = sum(float(a.get("size", 0)) for a in asks)
            total_bid_depth = sum(float(b.get("size", 0)) for b in bids)
            print(f"  Ask Depth: {total_ask_depth:.1f} contracts ({len(asks)} levels)")
            print(f"  Bid Depth: {total_bid_depth:.1f} contracts ({len(bids)} levels)")
            print()
            print(f"  {'Order Size':12} | {'Fill Price':12} | {'Slippage':10}")
            print(f"  {'-'*12} | {'-'*12} | {'-'*10}")

            market_slippages = {}

            for order_size in ORDER_SIZES:
                fill_price, contracts = calculate_fill_price(asks, order_size)

                if fill_price:
                    slippage = calculate_slippage(fill_price, best_ask)
                    market_slippages[order_size] = slippage
                    all_slippages[order_size].append(slippage)
                    print(f"  ${order_size:<11} | {fill_price:<12.3f} | {slippage:.2f}%")
                else:
                    print(f"  ${order_size:<11} | {'N/A':12} | {'N/A':10}")

            print()
            analyzed_count += 1
            break  # Only analyze one outcome per market

    if analyzed_count == 0:
        print(f"{RED}[ERROR]{RESET} Could not analyze any markets (no liquidity)")
        return

    # Print summary
    print(f"{BOLD}Durchschnitt ueber {analyzed_count} Maerkte:{RESET}")

    for order_size in ORDER_SIZES:
        slippages = all_slippages[order_size]
        if slippages:
            avg_slippage = sum(slippages) / len(slippages)
            max_slippage = max(slippages)
            print(f"  ${order_size}: {avg_slippage:.2f}% (max: {max_slippage:.2f}%)")
        else:
            print(f"  ${order_size}: N/A")

    print()

    # Return data for documentation
    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "market_count": analyzed_count,
        "slippages": {
            size: {
                "avg": sum(s)/len(s) if s else None,
                "max": max(s) if s else None
            }
            for size, s in all_slippages.items()
        }
    }


if __name__ == "__main__":
    result = analyze_markets()
    if result:
        print(f"{GREEN}[SUCCESS]{RESET} Analysis complete")
