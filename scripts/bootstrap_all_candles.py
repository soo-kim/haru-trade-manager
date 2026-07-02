from __future__ import annotations

import asyncio
from datetime import datetime

from app.core.rate_limited_client import RateLimitedClient
from app.core.settings import settings
from app.db.session import SessionLocal
from app.integrations.kiwoom.client import KiwoomApiClient
from app.integrations.kiwoom.market_data import KiwoomMarketDataGateway
from app.repositories.candle import CandleRepository
from app.repositories.universe import UniverseRepository
from app.services.universe_bootstrap import bootstrap_candles_on_first_run

TIMEFRAMES = ("1d", "3m", "5m", "15m", "60m")
BATCH_SIZE = 10


async def main() -> None:
    with SessionLocal() as db:
        tickers = UniverseRepository().list_universe_tickers(db, limit=20_000)
    total = len(tickers)
    print(f"[{datetime.now().isoformat()}] bootstrap_all_candles start tickers={total} timeframes={TIMEFRAMES}", flush=True)
    inserted_total = 0
    updated_total = 0
    failed_total = 0
    errors: list[str] = []
    for idx in range(0, total, BATCH_SIZE):
        chunk = tickers[idx : idx + BATCH_SIZE]
        status = await bootstrap_candles_on_first_run(
            tickers=chunk,
            timeframes=TIMEFRAMES,
            session_factory=SessionLocal,
            candle_repo=CandleRepository(),
            kiwoom_app_key=settings.kiwoom_app_key,
            kiwoom_app_secret=settings.kiwoom_app_secret,
            rate_limited_client_factory=RateLimitedClient,
            kiwoom_api_client_factory=KiwoomApiClient,
            kiwoom_market_data_gateway_factory=KiwoomMarketDataGateway,
        )
        inserted_total += int(status.get("candles_inserted", 0) or 0)
        updated_total += int(status.get("candles_updated", 0) or 0)
        batch_errors = [str(x) for x in status.get("errors", [])]
        failed_total += len(batch_errors)
        errors.extend(batch_errors[: max(0, 20 - len(errors))])
        print(
            f"[{datetime.now().isoformat()}] batch {idx + 1}-{min(idx + BATCH_SIZE, total)}/{total} "
            f"ok={status.get('ok')} msg={status.get('message')} "
            f"inserted_total={inserted_total} updated_total={updated_total} failed_total={failed_total}",
            flush=True,
        )
    print(
        f"[{datetime.now().isoformat()}] bootstrap_all_candles done "
        f"tickers={total} inserted={inserted_total} updated={updated_total} failed={failed_total} errors={errors[:20]}",
        flush=True,
    )


if __name__ == "__main__":
    asyncio.run(main())
