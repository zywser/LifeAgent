import asyncio
import redis as redis_lib
from functools import lru_cache
from langchain_redis import RedisVectorStore
from langgraph.checkpoint.redis.aio import AsyncRedisSaver
from ..config import settings
from ..llm import embeddings

_checkpointer = None


def _store(index_name: str):
    try:
        return RedisVectorStore(embeddings, redis_url=settings.redis_url, index_name=index_name, vector_dimensions=1536)
    except TypeError:
        return RedisVectorStore(embeddings, redis_url=settings.redis_url, index_name=index_name)

@lru_cache(maxsize=256)
def get_notes_store(uid: int):
    return _store(f"user:{uid}:notes_idx")

@lru_cache(maxsize=256)
def get_memory_store(uid: int):
    return _store(f"user:{uid}:memory_idx")


def delete_note_vectors(uid: int, doc_id: str) -> int:
    """删除某笔记的所有 chunk 向量，返回删除的 key 数。

    笔记上传时每个 chunk 的 key 形如
    `{key_prefix}:{doc_id}_c{i}`，这里用 scan 匹配并删除，
    避免笔记删除后向量仍残留在向量库里。
    """
    store = get_notes_store(uid)
    key_prefix = store.key_prefix or f"user:{uid}:notes_idx"
    client = redis_lib.from_url(settings.redis_url)
    pattern = f"{key_prefix}:{doc_id}_c*"
    keys = list(client.scan_iter(pattern))
    if keys:
        client.delete(*keys)
    return len(keys)

async def get_checkpointer():
    global _checkpointer
    if _checkpointer is None:
        _checkpointer = AsyncRedisSaver(redis_url=settings.redis_url)
        await _checkpointer.asetup()
    return _checkpointer
