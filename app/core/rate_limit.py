from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.constants import RATE_LIMIT_DEFAULT


def rate_limit_key(request: Request) -> str:
    """Limit per user when authenticated, else per client IP.

    get_current_user sets request.state.user_id once the token is verified.
    """
    user_id = getattr(request.state, "user_id", None)
    return f"user:{user_id}" if user_id else f"ip:{get_remote_address(request)}"


limiter = Limiter(key_func=rate_limit_key, default_limits=[RATE_LIMIT_DEFAULT])
