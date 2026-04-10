"""diskcache wrapper with TTL management for CMS rate data."""
from __future__ import annotations
import diskcache
from pathlib import Path
from config import settings

_cache: diskcache.Cache | None = None


def get_cache() -> diskcache.Cache:
    global _cache
    if _cache is None:
        _cache = diskcache.Cache(str(settings.cache_dir))
    return _cache


def cache_get(key: str):
    return get_cache().get(key)


def cache_set(key: str, value, expire_seconds: int | None = None):
    get_cache().set(key, value, expire=expire_seconds)


def cache_delete(key: str):
    try:
        del get_cache()[key]
    except KeyError:
        pass


def cache_clear():
    get_cache().clear()
