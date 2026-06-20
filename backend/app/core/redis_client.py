import logging
import redis.asyncio as redis
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Asynchronous Redis client
redis_client = redis.from_url(settings.redis_url, decode_responses=True)

async def check_redis_connection() -> bool:
    """Check if connection to Redis is healthy."""
    try:
        await redis_client.ping()
        return True
    except Exception as e:
        logger.error("Failed to connect to Redis: %s", e)
        return False
