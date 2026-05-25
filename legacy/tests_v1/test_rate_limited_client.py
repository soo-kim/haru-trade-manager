import asyncio
import time

from app.core.rate_limited_client import RateLimitedClient


def test_rate_limited_client_spacing():
    client = RateLimitedClient(min_interval_seconds=0.05)
    call_times: list[float] = []

    async def fake_call() -> str:
        call_times.append(time.monotonic())
        return "ok"

    async def run_calls():
        await client.enqueue(fake_call, is_order=False)
        await client.enqueue(fake_call, is_order=False)

    asyncio.run(run_calls())
    assert len(call_times) == 2
    assert (call_times[1] - call_times[0]) >= 0.045
