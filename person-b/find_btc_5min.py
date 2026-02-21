"""
Deep search for BTC 5-minute Up/Down markets on Polymarket
"""

import httpx
import json
from datetime import datetime, timezone


def search_all_endpoints():
    """Search multiple Polymarket API endpoints"""

    print("=" * 60)
    print("Searching for BTC 5-minute Up/Down Markets")
    print("=" * 60)

    endpoints = [
        # Gamma API
        ("Gamma Markets", "https://gamma-api.polymarket.com/markets", {"closed": "false", "limit": 500}),
        ("Gamma Events", "https://gamma-api.polymarket.com/events", {"closed": "false", "limit": 100}),

        # CLOB API
        ("CLOB Markets", "https://clob.polymarket.com/markets", {"closed": "false", "limit": 500}),

        # Sampling API (potential endpoint for minute markets)
        ("Sampling", "https://clob.polymarket.com/sampling-markets", {}),
        ("Simplified", "https://clob.polymarket.com/sampling-simplified-markets", {}),
    ]

    btc_markets_found = []

    for name, url, params in endpoints:
        print(f"\n--- {name} ---")
        print(f"URL: {url}")

        try:
            resp = httpx.get(url, params=params, timeout=30)
            print(f"Status: {resp.status_code}")

            if resp.status_code == 200:
                try:
                    data = resp.json()

                    # Handle different response formats
                    if isinstance(data, dict):
                        items = data.get("data", data.get("markets", data.get("events", [])))
                        if not isinstance(items, list):
                            items = [data]
                    else:
                        items = data

                    print(f"Items: {len(items)}")

                    # Search for BTC 5-min markets
                    for item in items:
                        # Get searchable text
                        question = item.get("question", "") or item.get("title", "") or ""
                        description = item.get("description", "") or ""
                        slug = item.get("slug", "") or item.get("market_slug", "") or ""
                        search_text = f"{question} {description} {slug}".upper()

                        # Check for BTC/Bitcoin AND minute/5-min keywords
                        is_btc = "BTC" in search_text or "BITCOIN" in search_text
                        is_5min = any(x in search_text for x in [
                            "5 MIN", "5MIN", "FIVE MIN", "5-MIN",
                            "MINUTE", "UP OR DOWN", "UP/DOWN"
                        ])
                        is_active = not item.get("closed", True) or item.get("active", False)

                        # Also check for crypto price markets
                        is_crypto_price = any(x in search_text for x in [
                            "PRICE OF", "ABOVE", "BELOW", "HIGHER", "LOWER"
                        ]) and is_btc

                        if is_btc and (is_5min or is_crypto_price):
                            print(f"\n  [FOUND] {question[:70]}")
                            print(f"    ID: {item.get('conditionId', item.get('condition_id', item.get('id', '?')))}")
                            print(f"    Slug: {slug[:50]}")
                            print(f"    Closed: {item.get('closed')}")
                            btc_markets_found.append(item)

                except json.JSONDecodeError:
                    print(f"  Invalid JSON response")
            else:
                print(f"  Response: {resp.text[:200]}")

        except httpx.TimeoutException:
            print(f"  Timeout")
        except Exception as e:
            print(f"  Error: {type(e).__name__}: {e}")

    # Summary
    print("\n" + "=" * 60)
    print(f"SUMMARY: Found {len(btc_markets_found)} potential BTC markets")
    print("=" * 60)

    # Check for special sampling endpoint
    print("\n--- Checking Dedicated Endpoints ---")

    special_endpoints = [
        "https://clob.polymarket.com/tick-size-groups",
        "https://clob.polymarket.com/neg-risk",
        "https://clob.polymarket.com/reward-info",
    ]

    for url in special_endpoints:
        try:
            resp = httpx.get(url, timeout=10)
            print(f"{url.split('/')[-1]}: {resp.status_code}")
            if resp.status_code == 200:
                data = resp.json()
                print(f"  Response type: {type(data).__name__}")
                if isinstance(data, list):
                    print(f"  Items: {len(data)}")
                elif isinstance(data, dict):
                    print(f"  Keys: {list(data.keys())[:5]}")
        except Exception as e:
            print(f"  {url.split('/')[-1]}: {type(e).__name__}")

    return btc_markets_found


if __name__ == "__main__":
    markets = search_all_endpoints()

    if markets:
        # Save found markets
        with open("btc_markets_deep.json", "w", encoding="utf-8") as f:
            json.dump({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "markets": markets
            }, f, indent=2, ensure_ascii=False)
        print(f"\nSaved to btc_markets_deep.json")
