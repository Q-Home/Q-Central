import httpx
from .config import get_settings


async def authorize_member(node_id: str) -> bool:
    settings = get_settings()
    if not settings.zerotier_api_token or not settings.zerotier_network_id:
        return False
    url = f"http://127.0.0.1:9993/controller/network/{settings.zerotier_network_id}/member/{node_id}"
    headers = {"X-ZT1-Auth": settings.zerotier_api_token}
    payload = {"authorized": True}
    async with httpx.AsyncClient(timeout=5) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
    return True
