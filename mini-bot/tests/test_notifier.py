from __future__ import annotations

from pathlib import Path
from unittest import mock

from bot.notifier import TelegramNotifier


def test_notifier_freezes_after_failures(tmp_path: Path) -> None:
    freeze = tmp_path / "freeze.flag"
    notifier = TelegramNotifier("token", 123, freeze_path=freeze, max_failures=2)
    with mock.patch("bot.notifier.request.urlopen", side_effect=RuntimeError("boom")):
        assert notifier.send_message("hello") is False
        assert notifier.is_frozen() is False
        assert notifier.send_message("hello") is False
        assert notifier.is_frozen() is True


def test_notifier_skips_when_not_configured() -> None:
    notifier = TelegramNotifier(None, None)
    assert notifier.send_message("hi") is False
