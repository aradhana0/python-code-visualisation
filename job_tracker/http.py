from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

USER_AGENT = "job-tracker/1.0 (personal job search; respects robots and rate limits)"


class FetchError(RuntimeError):
    pass


def get_json(url: str, *, data: dict | None = None, timeout: int = 30, retries: int = 2):
    """GET (or POST when ``data`` is given) a URL and decode JSON, with small retries."""
    body = json.dumps(data).encode() if data is not None else None
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    last: Exception | None = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=body, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code in (400, 401, 403, 404):
                raise FetchError(f"{url}: HTTP {exc.code}") from exc
            last = exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last = exc
        time.sleep(2 ** attempt)
    raise FetchError(f"{url}: {last}")
