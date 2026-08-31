"""Room/seat data cache with background refresh.

Extracted from killer.py:355-369 (updateRooms) + periodic refresh.
"""

from __future__ import annotations

import logging
import threading
from time import sleep
from typing import Dict, List, Optional, Callable

from seathunter.api.client import ApiClient

logger = logging.getLogger("seathunter.api")

REFRESH_INTERVAL = 4 * 3600  # 4 hours


class RoomCache:
    """Caches room/seat data with background refresh."""

    def __init__(self, api_client: ApiClient):
        self.api = api_client
        self.rooms: Dict = {}
        self._refresh_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._ready_event = threading.Event()
        self._on_ready_callbacks: List[Callable] = []

    @property
    def is_ready(self) -> bool:
        return self._ready_event.is_set()

    def refresh(self, max_retries: int = 3) -> List[str]:
        """Refresh room data (blocking). Returns list of room names."""
        for attempt in range(max_retries):
            try:
                self.rooms = self.api.query_rooms()
                self.api.query_seats(self.rooms)
                self._ready_event.set()
                self._notify_ready()
                return list(self.rooms.keys())
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning("Room refresh failed (attempt %d), retrying in 5s: %s",
                                  attempt + 1, e)
                    sleep(5)
                else:
                    logger.error("Room refresh failed after %d attempts: %s", max_retries, e)
                    self.rooms = {}
                    return []
        return []

    def start_background_refresh(self):
        """Start background thread that refreshes room data periodically."""
        if self._refresh_thread and self._refresh_thread.is_alive():
            return

        self._stop_event.clear()

        def _bg_loop():
            while not self._stop_event.is_set():
                try:
                    self.refresh()
                except Exception as e:
                    logger.warning("Background room refresh error: %s", e)
                self._stop_event.wait(REFRESH_INTERVAL)

        self._refresh_thread = threading.Thread(target=_bg_loop, daemon=True, name="RoomCache")
        self._refresh_thread.start()
        logger.info("Background room refresh started (interval: %dh)", REFRESH_INTERVAL // 3600)

    def stop_background_refresh(self):
        """Stop the background refresh thread."""
        self._stop_event.set()
        if self._refresh_thread and self._refresh_thread.is_alive():
            self._refresh_thread.join(timeout=5)
        logger.debug("Background room refresh stopped")

    def wait_until_ready(self, timeout: float = 120):
        """Block until room data is ready or timeout."""
        self._ready_event.wait(timeout=timeout)

    def on_ready(self, callback: Callable):
        """Register a callback for when room data becomes available."""
        self._on_ready_callbacks.append(callback)
        if self.is_ready:
            callback()

    def _notify_ready(self):
        for cb in self._on_ready_callbacks:
            try:
                cb()
            except Exception as e:
                logger.warning("Room ready callback error: %s", e)

    def get_floor_names(self, room_name: str) -> List[str]:
        if room_name not in self.rooms:
            return []
        return list(self.rooms[room_name].get("floors", {}).keys())

    def get_seats(self, room_name: str, floor_name: str) -> List[Dict]:
        if room_name not in self.rooms:
            return []
        floors = self.rooms[room_name].get("floors", {})
        if floor_name not in floors:
            return []
        return floors[floor_name].get("seats", [])

    def get_room_names(self) -> List[str]:
        return list(self.rooms.keys())
