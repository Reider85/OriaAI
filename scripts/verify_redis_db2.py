"""Verify Redis DB 2 (semantic cache) is reachable."""
import asyncio
import redis.asyncio as redis
from llm_client.config import settings


async def main():
    s = settings
    r = redis.from_url(s.redis_semantic_cache_url)
    pong = await r.ping()
    assert pong, "Redis DB 2 not reachable"
    await r.set("sem_cache:__probe__", "ok", ex=60)
    val = await r.get("sem_cache:__probe__")
    assert val == b"ok", f"unexpected probe value: {val!r}"
    await r.delete("sem_cache:__probe__")
    print(f"OK — Redis DB 2 reachable at {s.redis_semantic_cache_url}")


if __name__ == "__main__":
    asyncio.run(main())