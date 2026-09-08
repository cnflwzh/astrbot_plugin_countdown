import asyncio

from countdown.ticker import DailyTicker


def test_callback_failure_still_waits_before_retry():
    async def scenario():
        attempts = 0

        async def tick(_now):
            nonlocal attempts
            attempts += 1
            if attempts > 100:
                raise asyncio.CancelledError
            raise RuntimeError("broken callback")

        ticker = DailyTicker(tick, interval=60)
        ticker.start()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        await ticker.stop()
        assert attempts == 1

    asyncio.run(scenario())
