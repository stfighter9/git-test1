"""Telegram notifier for the trading bot."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional
from urllib import parse, request
from urllib.error import URLError

LOGGER = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(
        self,
        token: Optional[str],
        chat_id: Optional[int],
        freeze_path: Path | str = Path("data/notify.freeze"),
        max_failures: int = 3,
    ) -> None:
        self.token = token
        self.chat_id = chat_id
        self.freeze_path = Path(freeze_path)
        self.max_failures = max_failures
        self._failures = 0

    def _freeze(self) -> None:
        self.freeze_path.parent.mkdir(parents=True, exist_ok=True)
        self.freeze_path.write_text("freeze")

    def is_frozen(self) -> bool:
        return self.freeze_path.exists()

    def send_message(self, text: str) -> bool:
        if not self.token or not self.chat_id:
            LOGGER.warning("Telegram not configured; skipping message")
            return False
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        data = parse.urlencode({"chat_id": self.chat_id, "text": text}).encode()
        try:
            with request.urlopen(url, data=data, timeout=10) as resp:  # pragma: no cover - network stub
                payload = json.loads(resp.read().decode())
            if not payload.get("ok", False):  # pragma: no cover - depends on API
                raise URLError(f"Telegram error: {payload}")
        except Exception as exc:  # pragma: no cover
            self._failures += 1
            LOGGER.error("Telegram send failed (%s/%s): %s", self._failures, self.max_failures, exc)
            if self._failures >= self.max_failures:
                self._freeze()
            return False
        self._failures = 0
        return True


__all__ = ["TelegramNotifier"]
