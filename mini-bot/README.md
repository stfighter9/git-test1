# Mini Bot

A lightweight H4/D1 swing trading bot designed for low-cost VPS deployments. The system ingests OHLCV data via ccxt, derives technical features, loads a pre-trained LightGBM-style model, applies policy + risk checks, and sends post-only ladder orders.

## Requirements

* Python 3.11
* SQLite 3
* Optional: `ccxt` for exchange connectivity

Install Python dependencies:

```bash
pip install -r requirements.txt
```

## Configuration

Copy `.env.example` to `.env` and fill in API keys. The runtime also reads `config.yaml` for overrides (risk, ATR settings, ladder levels). Model weights reside in `models/model.pkl`.

## Running a Cycle

```bash
PYTHONPATH=. python -m bot.run_cycle
```

On production, deploy the `systemd` service/timer in `deploy/` and install with `scripts/install.sh`.

## Testing

```bash
PYTHONPATH=. pytest
```

## Telegram Commands

* `/snap` – snapshot balances and orders
* `/flat` – flatten and cancel
* `/halt` / `/resume` – toggle freeze

## Gauntlet Checklist

1. Backfill after network loss
2. Enforce min notional checks
3. Cancel post-only ladder after timeout
4. Freeze on daily loss limit breach
5. Continue running if Telegram fails (freeze new orders)
