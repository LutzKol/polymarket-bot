"""WebSocket manager with reconnect logic for multi-feed pipeline."""

from __future__ import annotations

import asyncio
import inspect
import json
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

import websockets
from websockets.exceptions import ConnectionClosed


MessageHandler = Callable[[Any], Optional[Awaitable[None]]]


@dataclass
class FeedConfig:
    name: str
    url: str
    on_message: MessageHandler
    parse_json: bool = True
    ping_interval: int = 20
    ping_timeout: int = 10


class WebSocketManager:
    """Run and supervise multiple websocket feeds with auto-reconnect."""

    def __init__(
        self,
        *,
        reconnect_base_seconds: float = 1.0,
        reconnect_max_seconds: float = 30.0,
        logger: Optional[Callable[[str], None]] = None,
    ):
        self.reconnect_base_seconds = reconnect_base_seconds
        self.reconnect_max_seconds = reconnect_max_seconds
        self.logger = logger or print
        self._stop_event: Optional[asyncio.Event] = None

    def _get_stop_event(self) -> asyncio.Event:
        if self._stop_event is None:
            self._stop_event = asyncio.Event()
        return self._stop_event

    def stop(self) -> None:
        if self._stop_event is not None:
            self._stop_event.set()

    async def run_feed(self, feed: FeedConfig) -> None:
        stop_event = self._get_stop_event()
        backoff = self.reconnect_base_seconds

        while not stop_event.is_set():
            try:
                self.logger(f"[WS:{feed.name}] connecting -> {feed.url}")
                async with websockets.connect(
                    feed.url,
                    ping_interval=feed.ping_interval,
                    ping_timeout=feed.ping_timeout,
                ) as ws:
                    self.logger(f"[WS:{feed.name}] connected")
                    backoff = self.reconnect_base_seconds

                    while not stop_event.is_set():
                        try:
                            raw_msg = await asyncio.wait_for(ws.recv(), timeout=1.0)
                        except asyncio.TimeoutError:
                            continue
                        except ConnectionClosed:
                            break

                        payload: Any = raw_msg
                        if feed.parse_json:
                            payload = json.loads(raw_msg)
                        await self._dispatch(feed.on_message, payload)

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if stop_event.is_set():
                    break
                delay = min(backoff, self.reconnect_max_seconds)
                self.logger(f"[WS:{feed.name}] error: {exc} -> reconnect in {delay:.1f}s")
                await asyncio.sleep(delay)
                backoff = min(backoff * 2, self.reconnect_max_seconds)

    async def run_all(self, feeds: list[FeedConfig]) -> None:
        if not feeds:
            raise ValueError("feeds must not be empty")
        await asyncio.gather(*(self.run_feed(feed) for feed in feeds))

    async def _dispatch(self, handler: MessageHandler, payload: Any) -> None:
        result = handler(payload)
        if inspect.isawaitable(result):
            await result
