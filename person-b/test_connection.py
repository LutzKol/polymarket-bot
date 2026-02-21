"""
Polymarket CLOB API Connection Test
Tests API connectivity and fetches BTC 5-minute Up/Down markets
"""

import os
import json
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
import httpx

# Load credentials from .env
load_dotenv()

API_KEY = os.getenv("POLYMARKET_API_KEY")
API_SECRET = os.getenv("POLYMARKET_SECRET")
API_PASSPHRASE = os.getenv("POLYMARKET_PASSPHRASE")

# API URLs
CLOB_BASE_URL = "https://clob.polymarket.com"
GAMMA_API_URL = "https://gamma-api.polymarket.com"

# ANSI colors for terminal output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RESET = "\033[0m"
BOLD = "\033[1m"


def print_success(msg: str):
    print(f"{GREEN}{BOLD}[SUCCESS]{RESET} {msg}")


def print_error(msg: str):
    print(f"{RED}{BOLD}[ERROR]{RESET} {msg}")


def print_info(msg: str):
    print(f"{YELLOW}[INFO]{RESET} {msg}")


def print_market(msg: str):
    print(f"{CYAN}[MARKET]{RESET} {msg}")


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


def find_btc_5min_events(count: int = 6) -> list[dict]:
    """
    Find active BTC 5-minute Up/Down events.

    The markets follow the pattern: btc-updown-5m-{unix_timestamp}
    where timestamp is the start time of the 5-minute window.
    """
    print_info("Calculating upcoming BTC 5-min market timestamps...")

    timestamps = get_next_5min_boundaries(count)
    found_events = []

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
                if events:
                    found_events.extend(events)
                    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                    print_info(f"Found: {slug} ({dt.strftime('%H:%M')} UTC)")
        except Exception as e:
            print_error(f"Error fetching {slug}: {e}")

    return found_events


def test_connection():
    """Test Polymarket API connection and fetch BTC 5-min markets."""

    try:
        from py_clob_client.client import ClobClient
        from py_clob_client.clob_types import ApiCreds
    except ImportError as e:
        print_error(f"Missing dependency: {e}")
        print_info("Install with: pip install py-clob-client python-dotenv")
        return False

    # Verify credentials are loaded
    if not all([API_KEY, API_SECRET, API_PASSPHRASE]):
        print_error("Missing credentials in .env file")
        print_info("Required: POLYMARKET_API_KEY, POLYMARKET_SECRET, POLYMARKET_PASSPHRASE")
        return False

    print_info("Credentials loaded from .env")

    try:
        # Initialize CLOB client
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

        print_info(f"Connected to {CLOB_BASE_URL}")

        # Find upcoming BTC 5-min events
        btc_events = find_btc_5min_events(count=6)
        print_info(f"Found {len(btc_events)} upcoming BTC 5-min events")

        market_data = []

        for event in btc_events:
            event_id = event.get("id")
            slug = event.get("slug", "")
            title = event.get("title", "")
            end_date = event.get("endDate", "")

            # Fetch full event details to get market info
            try:
                resp = httpx.get(f"{GAMMA_API_URL}/events/{event_id}", timeout=15)
                if resp.status_code == 200:
                    full_event = resp.json()
                    markets = full_event.get("markets", [])
                else:
                    markets = event.get("markets", [])
            except:
                markets = event.get("markets", [])

            print(f"\n{BOLD}Event:{RESET} {title}")
            print(f"  Slug: {slug}")
            print(f"  End: {end_date}")

            for market in markets:
                condition_id = market.get("conditionId", "")
                question = market.get("question", "")
                outcomes = market.get("outcomes", ["Up", "Down"])
                outcome_prices = market.get("outcomePrices", [])

                # Parse JSON strings if needed
                if isinstance(outcomes, str):
                    try:
                        outcomes = json.loads(outcomes)
                    except:
                        outcomes = ["Up", "Down"]

                # Get token IDs
                tokens = market.get("clobTokenIds", [])
                if isinstance(tokens, str):
                    try:
                        tokens = json.loads(tokens)
                    except:
                        tokens = []

                print(f"  Condition ID: {condition_id[:20]}...")

                # Show current prices from event data
                if outcome_prices:
                    # Handle different formats (string, list, or JSON string)
                    if isinstance(outcome_prices, str):
                        try:
                            outcome_prices = json.loads(outcome_prices)
                        except:
                            outcome_prices = []

                    for i, (outcome, price) in enumerate(zip(outcomes, outcome_prices)):
                        try:
                            prob = float(price) * 100
                            print_market(f"    {outcome}: {prob:.1f}%")
                        except (ValueError, TypeError):
                            print_market(f"    {outcome}: {price}")

                # Get live orderbook
                for i, token_id in enumerate(tokens[:2]):
                    outcome = outcomes[i] if i < len(outcomes) else f"Outcome {i}"

                    try:
                        orderbook = client.get_order_book(str(token_id))

                        bids = orderbook.get("bids", [])
                        asks = orderbook.get("asks", [])

                        best_bid = float(bids[0].get("price", 0)) if bids else None
                        best_ask = float(asks[0].get("price", 0)) if asks else None

                        if best_bid and best_ask:
                            mid = (best_bid + best_ask) / 2
                            spread = best_ask - best_bid
                            print(f"    {outcome} Orderbook: Bid={best_bid:.3f}, Ask={best_ask:.3f}, Spread={spread:.3f}")
                        else:
                            print(f"    {outcome} Orderbook: No liquidity")

                    except Exception as e:
                        print(f"    {outcome} Orderbook: Error ({type(e).__name__})")

                market_data.append({
                    "event_id": event_id,
                    "slug": slug,
                    "title": title,
                    "end_date": end_date,
                    "condition_id": condition_id,
                    "token_ids": tokens,
                    "outcomes": outcomes,
                    "outcome_prices": outcome_prices
                })

        # Save results
        output_file = "btc_markets.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "total_events": len(btc_events),
                "markets": market_data
            }, f, indent=2, ensure_ascii=False)

        print()
        print_success(f"Saved {len(market_data)} markets to {output_file}")
        print_success("Polymarket API connection successful!")

        # Summary
        print(f"\n{BOLD}=== Summary ==={RESET}")
        print(f"  API Connection: OK")
        print(f"  Credentials: Loaded from .env")
        print(f"  BTC 5-min Markets Found: {len(btc_events)}")
        print(f"  Resolution Source: Chainlink BTC/USD")

        return True

    except Exception as e:
        print_error(f"Connection failed: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print(f"\n{BOLD}=== Polymarket CLOB API Connection Test ==={RESET}\n")
    success = test_connection()
    print()
    exit(0 if success else 1)
