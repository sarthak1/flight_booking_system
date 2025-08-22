import json
import threading
import time
import redis
from app.core.settings import settings

r = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)

SESSION_TTL_SECONDS = 60 * 60 * 6  # 6 hours

# In-process fallback store if Redis is down/unreachable
_fallback_store: dict[str, tuple[dict, float]] = {}
_fallback_lock = threading.RLock()
_use_fallback = True


def _enable_fallback(reason: str = ""):
    global _use_fallback
    _use_fallback = True


def _fallback_cleanup():
    now = time.time()
    with _fallback_lock:
        expired = [k for k, (_, exp) in _fallback_store.items() if exp < now]
        for k in expired:
            _fallback_store.pop(k, None)


def session_key(phone: str) -> str:
    return f"wa:{phone}"


def get_session(phone: str) -> dict:
    if _use_fallback:
        _fallback_cleanup()
        with _fallback_lock:
            item = _fallback_store.get(phone)
            return item[0] if item else {}
    try:
        data = r.get(session_key(phone))
        return json.loads(data) if data else {}
    except Exception:
        _enable_fallback("get_failed")
        return get_session(phone)


def set_session(phone: str, data: dict):
    if _use_fallback:
        with _fallback_lock:
            _fallback_store[phone] = (data, time.time() + SESSION_TTL_SECONDS)
        return
    try:
        r.setex(session_key(phone), SESSION_TTL_SECONDS, json.dumps(data))
    except Exception:
        _enable_fallback("set_failed")
        set_session(phone, data)


def clear_session(phone: str):
    if _use_fallback:
        with _fallback_lock:
            _fallback_store.pop(phone, None)
        return
    try:
        r.delete(session_key(phone))
    except Exception:
        _enable_fallback("del_failed")
        clear_session(phone)
