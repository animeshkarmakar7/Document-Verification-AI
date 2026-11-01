from app.services.gemini_rate_limiter import GeminiRequestPacer


def test_request_pacer_waits_between_requests(monkeypatch):
    current_time = [100.0]
    sleeps = []

    def fake_monotonic():
        return current_time[0]

    def fake_sleep(delay):
        sleeps.append(delay)
        current_time[0] += delay

    monkeypatch.setattr("app.services.gemini_rate_limiter.time.monotonic", fake_monotonic)
    monkeypatch.setattr("app.services.gemini_rate_limiter.time.sleep", fake_sleep)

    pacer = GeminiRequestPacer(min_interval_seconds=12.5)
    pacer.acquire()
    pacer.acquire()
    pacer.acquire()

    assert sleeps == [12.5, 12.5]


def test_request_pacer_can_be_disabled():
    pacer = GeminiRequestPacer(min_interval_seconds=0)
    pacer.acquire()
    pacer.acquire()
