"""Webhook 推送客户端"""
import httpx
import logging

from src.config import WEBHOOK_URL

logger = logging.getLogger(__name__)


async def push_webhook(payload: dict) -> bool:
    """向 Link 中间件推送 webhook（异步版）"""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(WEBHOOK_URL, json=payload)
            if resp.status_code < 300:
                logger.info(f"Webhook pushed: {payload.get('type')}")
                return True
            logger.warning(f"Webhook failed: {resp.status_code}")
            return False
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return False


def push_webhook_sync(payload: dict) -> bool:
    """同步版本（供 APScheduler 使用）"""
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.post(WEBHOOK_URL, json=payload)
            if resp.status_code < 300:
                logger.info(f"Webhook pushed: {payload.get('type')}")
                return True
            logger.warning(f"Webhook failed: {resp.status_code}")
            return False
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return False
