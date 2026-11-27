"""Telegram Bot API flood control (v3.9.1).

When Telegram answers "Flood control exceeded. Retry in N seconds" (`telegram.error.RetryAfter`) for a chat,
every further message to that chat during those N seconds fails too, and repeated violations make the next
wait longer. `FloodGate` is plugged into the bot's `Application` as its rate limiter: after a RetryAfter it
remembers until when that chat is blocked and fails every send / edit to it before then at once (the same
RetryAfter, no request sent), so progress edits and queue updates stop hitting Telegram until the wait is
over. Other calls (getUpdates, answerCallbackQuery, getMe...) are never held back. `blocked_for(chat_id)`
tells the queue worker how long to wait before retrying an item.
"""
import logging
import time

from telegram.error import RetryAfter
from telegram.ext import BaseRateLimiter

logger = logging.getLogger(__name__)

GATED = ('send', 'edit', 'copy', 'forward')     # endpoint prefixes that post into a chat

_until = {}         # chat id -> time.monotonic() before which nothing may be posted there


def seconds_of(error: RetryAfter) -> float:
    value = error.retry_after
    return float(value.total_seconds() if hasattr(value, 'total_seconds') else value)


def blocked_for(chat_id=None) -> float:
    """Seconds left of the flood wait of `chat_id` (any chat when None); 0 when the bot may post."""
    now = time.monotonic()
    if chat_id is None:
        return max([0.0] + [t - now for t in _until.values()])
    return max(0.0, _until.get(str(chat_id), 0.0) - now)


def note(chat_id, error: RetryAfter):
    """Remember a flood wait for `chat_id`."""
    seconds = seconds_of(error)
    until = time.monotonic() + seconds + 1
    key = str(chat_id)
    if until > _until.get(key, 0.0):
        logger.warning(f"Telegram 限流：{seconds:.0f} 秒內暫停發送訊息到聊天 {chat_id}")
        _until[key] = until


class FloodGate(BaseRateLimiter):
    async def initialize(self):
        pass

    async def shutdown(self):
        pass

    async def process_request(self, callback, args, kwargs, endpoint, data, rate_limit_args):
        chat_id = (data or {}).get('chat_id')
        if chat_id is None or not endpoint.startswith(GATED):
            return await callback(*args, **kwargs)
        left = blocked_for(chat_id)
        if left > 0:
            raise RetryAfter(int(left) + 1)
        try:
            return await callback(*args, **kwargs)
        except RetryAfter as e:
            note(chat_id, e)
            raise
