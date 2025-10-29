from __future__ import annotations

import random
import time

from bot.run_cycle import main


def run_with_jitter(min_delay: float = 5.0, max_delay: float = 15.0) -> None:
    delay = random.uniform(min_delay, max_delay)
    time.sleep(delay)
    main()


if __name__ == "__main__":  # pragma: no cover - CLI
    run_with_jitter()
