import time
import asyncio
from collections import defaultdict
from fastapi import Request, HTTPException, status, Depends
from src.core.security import get_current_user_id

_rate_limit_history: dict[tuple[str, str], list[float]] = defaultdict(list)
_rate_limit_lock = asyncio.Lock()

_global_executions = 0
_user_executions = defaultdict(int)

MAX_GLOBAL_EXECUTIONS = 50
MAX_USER_EXECUTIONS = 1

async def check_rate_limit(key: str, action: str, limit: int, window_seconds: int):
    now = time.time()
    async with _rate_limit_lock:
        history = _rate_limit_history[(key, action)]
        while history and history[0] < now - window_seconds:
            history.pop(0)
        if len(history) >= limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded for {action}"
            )
        history.append(now)

def rate_limiter(action: str, limit: int, window_seconds: int):
    """
    Dependency to enforce rate limits per IP and per user (if authenticated).
    """
    async def dependency(
        request: Request,
        user_id: str = Depends(get_current_user_id)
    ):
        ip = request.client.host if request.client else "unknown"
        await check_rate_limit(f"ip:{ip}", action, limit, window_seconds)
        if user_id:
            await check_rate_limit(f"user:{user_id}", action, limit, window_seconds)
        return True
    return dependency

class ExecutionTracker:
    def __init__(self):
        self.lock = asyncio.Lock()
    
    async def acquire(self, user_id: str):
        global _global_executions, _user_executions
        async with self.lock:
            if _global_executions >= MAX_GLOBAL_EXECUTIONS:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Global concurrent execution cap reached. Please try again later."
                )
            if _user_executions[user_id] >= MAX_USER_EXECUTIONS:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Concurrent execution limit reached ({MAX_USER_EXECUTIONS}). Wait for your current execution to finish."
                )
            _global_executions += 1
            _user_executions[user_id] += 1
            
    async def release(self, user_id: str):
        global _global_executions, _user_executions
        async with self.lock:
            _global_executions = max(0, _global_executions - 1)
            _user_executions[user_id] = max(0, _user_executions[user_id] - 1)

execution_tracker = ExecutionTracker()
