"""
Real-time Polymarket Orderbook Monitor + Binance Funding Rate
Phase 2: WebSocket Connection & Implied Probability Calculation
"""

import asyncio
import json
import os
import signal
import sys
from datetime import datetime, timezone
from typing import Optional

import httpx
import websockets
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Colors for terminal output
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
MAGENTA = "\033[95m"
RESET = "\033[0m"
BOLD = "\033[1m"

# Configuration
POLYMARKET_WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
BINANCE_FUNDING_URL = "https://fapi.binance.com/fapi/v1/fundingRate"
GAMMA_API = "https://gamma-api.polymarket.com"

# State
current_orderbook = {"up": {}, "down": {}}
running = True


def get_current_market_slug() -> str:
    """Generate the current 5-minute market slug based on timestamp"""
    now = datetime.now(timezone.utc)
    # Round down to nearest 5 minutes
    minutes = (now.minute // 5) * 5
    market_time = now.replace(minute=minutes, second=0, microsecond=0)
    timestamp = int(market_time.timestamp())
    return f"btc-updown-5m-{timestamp}"


async def fetch_market_tokens(slug: str) -> Optional[dict]:
    """Fetch token IDs for a specific market from Gamma API"""
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                f"{GAMMA_API}/events",
                params={"slug": slug},
                timeout=10.0
            )
            if resp.status_code == 200:
                data = resp.json()
                if data and len(data) > 0:
                    event = data[0]
                    markets = event.get("markets", [])
                    if markets:
                        market = markets[0]
                        tokens = market.get("clobTokenIds", [])

                        # clobTokenIds might be a JSON string, parse it
                        if isinstance(tokens, str):
                            tokens = json.loads(tokens)

                        outcomes = market.get("outcomes", "Up,Down")
                        if isinstance(outcomes, str):
                            outcomes = outcomes.split(",")

                        # Get current prices
                        prices = market.get("outcomePrices", ["0.5", "0.5"])
                        if isinstance(prices, str):
                            prices = json.loads(prices)

                        if len(tokens) >= 2:
                            return {
                                "slug": slug,
                                "condition_id": market.get("conditionId"),
                                "up_token": tokens[0],
                                "down_token": tokens[1],
                                "outcomes": outcomes,
                                "initial_prices": prices,
                                "end_date": market.get("endDate"),
                            }
        except Exception as e:
            print(f"{RED}[ERROR]{RESET} Failed to fetch market: {e}")
            import traceback
            traceback.print_exc()
    return None




def calculate_implied_probability(best_bid: float, best_ask: float) -> float:
    """
    Calculate implied probability from orderbook.
    Formula: implied_prob = best_bid / (best_bid + best_ask)
    """
    if best_bid + best_ask == 0:
        return 0.5
    return best_bid / (best_bid + best_ask)


def parse_orderbook_message(msg: dict) -> Optional[dict]:
    """Parse orderbook message and extract best bid/ask"""
    try:
        # The message contains: market, asset_id, timestamp, hash, bids, asks
        asset_id = msg.get("asset_id", "")
        bids = msg.get("bids", [])
        asks = msg.get("asks", [])

        if not asset_id:
            return None

        # Find best bid (highest price) and best ask (lowest price)
        # Bids and asks are lists of {"price": "0.XX", "size": "YYY"}
        best_bid = 0
        best_ask = 1
        bid_size = 0
        ask_size = 0

        if bids:
            # Sort bids descending by price to get best bid
            sorted_bids = sorted(bids, key=lambda x: float(x["price"]), reverse=True)
            best_bid = float(sorted_bids[0]["price"])
            bid_size = float(sorted_bids[0]["size"])

        if asks:
            # Sort asks ascending by price to get best ask
            sorted_asks = sorted(asks, key=lambda x: float(x["price"]))
            best_ask = float(sorted_asks[0]["price"])
            ask_size = float(sorted_asks[0]["size"])

        return {
            "asset_id": asset_id,
            "best_bid": best_bid,
            "best_ask": best_ask,
            "bid_size": bid_size,
            "ask_size": ask_size,
            "spread": best_ask - best_bid,
            "mid_price": (best_bid + best_ask) / 2,
            "timestamp": msg.get("timestamp", "")
        }
    except (KeyError, IndexError, ValueError, TypeError) as e:
        pass
    return None


async def fetch_orderbook_rest(client: httpx.AsyncClient, token_id: str) -> Optional[dict]:
    """Fetch orderbook via REST API"""
    try:
        resp = await client.get(
            "https://clob.polymarket.com/book",
            params={"token_id": token_id},
            timeout=10.0
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        pass
    return None


async def polymarket_orderbook_poller(market_info: dict):
    """Poll orderbook via REST API every 5 seconds"""
    global current_orderbook, running

    poll_count = 0

    async with httpx.AsyncClient() as client:
        while running:
            try:
                # Fetch both orderbooks
                up_book = await fetch_orderbook_rest(client, market_info["up_token"])
                down_book = await fetch_orderbook_rest(client, market_info["down_token"])

                if up_book:
                    parsed = parse_orderbook_message(up_book)
                    if parsed:
                        current_orderbook["up"] = parsed

                if down_book:
                    parsed = parse_orderbook_message(down_book)
                    if parsed:
                        current_orderbook["down"] = parsed

                # Display combined market state every poll
                poll_count += 1
                if current_orderbook["up"] and current_orderbook["down"]:
                    display_combined_probability()

            except Exception as e:
                print(f"{RED}[BOOK]{RESET} Error: {e}")

            await asyncio.sleep(5)  # Poll every 5 seconds


def display_combined_probability():
    """Display combined UP/DOWN probability"""
    up = current_orderbook.get("up", {})
    down = current_orderbook.get("down", {})

    if not up or not down:
        return

    now = datetime.now(timezone.utc).strftime("%H:%M:%S")

    up_bid = up.get("best_bid", 0)
    up_ask = up.get("best_ask", 1)
    down_bid = down.get("best_bid", 0)
    down_ask = down.get("best_ask", 1)

    up_spread = (up_ask - up_bid) * 100
    down_spread = (down_ask - down_bid) * 100

    # Calculate implied probability from mid prices
    up_mid = (up_bid + up_ask) / 2
    down_mid = (down_bid + down_ask) / 2

    # If spread is too wide (>50%), use bid as proxy
    if up_spread > 50:
        up_mid = up_bid if up_bid > 0.01 else 0.5
    if down_spread > 50:
        down_mid = down_bid if down_bid > 0.01 else 0.5

    # Normalize probabilities
    total = up_mid + down_mid
    up_prob = up_mid / total if total > 0 else 0.5
    down_prob = down_mid / total if total > 0 else 0.5

    # Determine market state
    if up_spread > 50 or down_spread > 50:
        status = f"{YELLOW}LOW LIQ{RESET}"
    else:
        status = f"{GREEN}ACTIVE{RESET}"

    print(f"{BOLD}[{now}]{RESET} {CYAN}MARKET{RESET} | "
          f"UP: bid={up_bid:.2f} ask={up_ask:.2f} | "
          f"DOWN: bid={down_bid:.2f} ask={down_ask:.2f} | "
          f"{status}")


async def polymarket_websocket(market_info: dict):
    """WebSocket connection for real-time updates (supplements REST polling)"""
    global current_orderbook, running

    reconnect_delay = 1
    max_delay = 60

    while running:
        try:
            print(f"\n{CYAN}[WS]{RESET} Connecting to Polymarket WebSocket...")

            async with websockets.connect(
                POLYMARKET_WS_URL,
                ping_interval=30,
                ping_timeout=10,
                close_timeout=5
            ) as ws:
                print(f"{GREEN}[WS]{RESET} Connected!")
                reconnect_delay = 1

                # Subscribe to both tokens
                subscribe_msg = {
                    "type": "subscribe",
                    "channel": "market",
                    "assets_ids": [market_info["up_token"], market_info["down_token"]]
                }
                await ws.send(json.dumps(subscribe_msg))
                print(f"{GREEN}[WS]{RESET} Subscribed (will receive updates on trades)")

                async for message in ws:
                    if not running:
                        break

                    try:
                        data = json.loads(message)

                        if isinstance(data, list):
                            for item in data:
                                if isinstance(item, dict) and item.get("asset_id"):
                                    await process_ws_message(item, market_info)
                        elif isinstance(data, dict) and data.get("asset_id"):
                            await process_ws_message(data, market_info)

                    except json.JSONDecodeError:
                        pass

        except websockets.ConnectionClosed as e:
            print(f"{YELLOW}[WS]{RESET} Connection closed: {e.code}")
        except Exception as e:
            print(f"{RED}[WS]{RESET} Error: {e}")

        if running:
            print(f"{YELLOW}[WS]{RESET} Reconnecting in {reconnect_delay}s...")
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, max_delay)


last_ws_display = {"up": 0, "down": 0}


async def process_ws_message(data: dict, market_info: dict):
    """Process a single WebSocket message"""
    global current_orderbook, last_ws_display
    import time

    parsed = parse_orderbook_message(data)
    if parsed:
        asset_id = parsed["asset_id"]

        # Determine if this is UP or DOWN token
        if asset_id == market_info["up_token"]:
            current_orderbook["up"] = parsed
            side = "up"
        elif asset_id == market_info["down_token"]:
            current_orderbook["down"] = parsed
            side = "down"
        else:
            return

        # Throttle display to max once per second per side
        now = time.time()
        if now - last_ws_display[side] >= 1.0:
            display_orderbook_update(side.upper(), parsed)
            last_ws_display[side] = now


def display_orderbook_update(side: str, data: dict):
    """Display orderbook update with implied probability"""
    now = datetime.now(timezone.utc).strftime("%H:%M:%S")

    implied_prob = calculate_implied_probability(data["best_bid"], data["best_ask"])
    spread_pct = data["spread"] * 100

    color = GREEN if side == "UP" else RED

    print(f"{BOLD}[{now}]{RESET} {color}{side:4}{RESET} | "
          f"Bid: {data['best_bid']:.3f} | "
          f"Ask: {data['best_ask']:.3f} | "
          f"Spread: {spread_pct:.2f}% | "
          f"Implied: {implied_prob:.1%}")


async def fetch_binance_funding_rate():
    """Fetch Binance Futures funding rate every 30 seconds"""
    global running

    async with httpx.AsyncClient() as client:
        while running:
            try:
                resp = await client.get(
                    BINANCE_FUNDING_URL,
                    params={"symbol": "BTCUSDT", "limit": 1},
                    timeout=10.0
                )

                if resp.status_code == 200:
                    data = resp.json()
                    if data and len(data) > 0:
                        funding = data[0]
                        rate = float(funding["fundingRate"]) * 100  # Convert to percentage
                        funding_time = datetime.fromtimestamp(
                            funding["fundingTime"] / 1000,
                            tz=timezone.utc
                        )

                        now = datetime.now(timezone.utc).strftime("%H:%M:%S")

                        # Color based on funding rate direction
                        if rate > 0:
                            color = GREEN  # Longs pay shorts
                        elif rate < 0:
                            color = RED    # Shorts pay longs
                        else:
                            color = YELLOW

                        print(f"{BOLD}[{now}]{RESET} {MAGENTA}FUNDING{RESET} | "
                              f"Rate: {color}{rate:+.4f}%{RESET} | "
                              f"Next: {funding_time.strftime('%H:%M UTC')}")
                else:
                    print(f"{YELLOW}[FUNDING]{RESET} HTTP {resp.status_code}")

            except Exception as e:
                print(f"{RED}[FUNDING]{RESET} Error: {e}")

            await asyncio.sleep(30)


async def market_refresh_loop():
    """Periodically refresh market info (every 5 minutes for new markets)"""
    global running

    while running:
        await asyncio.sleep(300)  # 5 minutes
        if running:
            print(f"\n{CYAN}[INFO]{RESET} Checking for new 5-min market...")
            # This would trigger a reconnection with new market
            # For now, just log - full implementation would restart WS


def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully"""
    global running
    print(f"\n{YELLOW}[INFO]{RESET} Shutting down...")
    running = False


async def main():
    """Main entry point"""
    global running

    print(f"\n{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}  Polymarket Real-Time Monitor - Phase 2{RESET}")
    print(f"{BOLD}{'='*60}{RESET}\n")

    # Get current market
    slug = get_current_market_slug()
    print(f"{CYAN}[INFO]{RESET} Current market: {slug}")

    # Fetch market tokens
    print(f"{CYAN}[INFO]{RESET} Fetching market tokens...")
    market_info = await fetch_market_tokens(slug)

    if not market_info:
        # Try next market if current one doesn't exist yet
        now = datetime.now(timezone.utc)
        minutes = ((now.minute // 5) + 1) * 5
        if minutes >= 60:
            minutes = 0
        next_time = now.replace(minute=minutes % 60, second=0, microsecond=0)
        next_timestamp = int(next_time.timestamp())
        slug = f"btc-updown-5m-{next_timestamp}"
        print(f"{YELLOW}[INFO]{RESET} Trying next market: {slug}")
        market_info = await fetch_market_tokens(slug)

    if not market_info:
        print(f"{RED}[ERROR]{RESET} Could not find active BTC 5-min market")
        print(f"{YELLOW}[INFO]{RESET} Markets may not be available yet. Try again later.")
        return

    print(f"{GREEN}[OK]{RESET} Market found: {market_info['slug']}")
    print(f"  UP Token:   {market_info['up_token'][:30]}...")
    print(f"  DOWN Token: {market_info['down_token'][:30]}...")

    print(f"\n{BOLD}Starting real-time monitoring...{RESET}")
    print(f"Press Ctrl+C to stop\n")
    print(f"{'='*70}")

    # Set up signal handler
    signal.signal(signal.SIGINT, signal_handler)

    # Run REST poller, WebSocket, and Funding Rate fetcher concurrently
    try:
        await asyncio.gather(
            polymarket_orderbook_poller(market_info),  # REST polling (primary)
            polymarket_websocket(market_info),          # WebSocket (for real-time updates)
            fetch_binance_funding_rate(),               # Funding rate
            return_exceptions=True
        )
    except asyncio.CancelledError:
        pass

    print(f"\n{GREEN}[INFO]{RESET} Monitor stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n{YELLOW}[INFO]{RESET} Interrupted by user")
