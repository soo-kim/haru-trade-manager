import asyncio
import time

from app.core.rate_limited_client import RateLimitedClient


def test_rate_limited_client_spacing():
    client = RateLimitedClient(min_interval=0.05)
    call_times: list[float] = []

    async def fake_call() -> str:
        call_times.append(time.monotonic())
        return "ok"

    async def run_calls() -> None:
        await client.enqueue(fake_call, is_order=False)
        await client.enqueue(fake_call, is_order=False)

    asyncio.run(run_calls())
    assert len(call_times) == 2
    assert (call_times[1] - call_times[0]) >= 0.045


def test_order_priority_when_pending_jobs_exist():
    client = RateLimitedClient(min_interval=0.0)
    started = asyncio.Event()
    release = asyncio.Event()
    executed: list[str] = []

    async def data_first() -> str:
        executed.append("data-1-start")
        started.set()
        await release.wait()
        executed.append("data-1-end")
        return "data-1"

    async def data_second() -> str:
        executed.append("data-2")
        return "data-2"

    async def order_job() -> str:
        executed.append("order")
        return "order"

    async def run_flow() -> None:
        t1 = asyncio.create_task(client.submit(data_first, is_order=False))
        await started.wait()
        t2 = asyncio.create_task(client.submit(data_second, is_order=False))
        t3 = asyncio.create_task(client.submit(order_job, is_order=True))
        release.set()
        await asyncio.gather(t1, t2, t3)

    asyncio.run(run_flow())
    assert executed.index("order") < executed.index("data-2")
