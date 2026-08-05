"""Small dependency-free concurrent load probe; point it at a non-production instance."""

import argparse
import asyncio
import statistics
import time
from pathlib import Path

import httpx


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("file", type=Path)
    parser.add_argument("--url", default="http://127.0.0.1:8000/scan/stream")
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--token")
    args = parser.parse_args()
    payload = args.file.read_bytes()
    semaphore = asyncio.Semaphore(args.concurrency)
    timings: list[float] = []
    statuses: dict[int, int] = {}
    headers = {"content-type": "application/octet-stream", "x-filename": args.file.name}
    if args.token:
        headers["authorization"] = f"Bearer {args.token}"

    async with httpx.AsyncClient(timeout=180) as client:

        async def scan() -> None:
            async with semaphore:
                started = time.perf_counter()
                response = await client.post(args.url, content=payload, headers=headers)
                timings.append(time.perf_counter() - started)
                statuses[response.status_code] = statuses.get(response.status_code, 0) + 1

        wall_started = time.perf_counter()
        await asyncio.gather(*(scan() for _ in range(args.requests)))
        elapsed = time.perf_counter() - wall_started

    ordered = sorted(timings)

    def percentile(p: float) -> float:
        return ordered[min(len(ordered) - 1, int(len(ordered) * p))]

    print(
        {
            "requests": args.requests,
            "seconds": round(elapsed, 3),
            "requests_per_second": round(args.requests / elapsed, 2),
            "statuses": statuses,
            "mean_seconds": round(statistics.mean(timings), 3),
            "p95_seconds": round(percentile(0.95), 3),
            "p99_seconds": round(percentile(0.99), 3),
        }
    )


if __name__ == "__main__":
    asyncio.run(main())
