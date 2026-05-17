import argparse
import asyncio

import httpx

from app.config import settings

BASE_URL = "https://www.strava.com/api/v3/push_subscriptions"


async def list_subscriptions(client: httpx.AsyncClient) -> list[dict]:
    response = await client.get(
        BASE_URL,
        params={"client_id": settings.strava_client_id, "client_secret": settings.strava_client_secret},
    )
    response.raise_for_status()
    return response.json()


async def delete_subscription(client: httpx.AsyncClient, subscription_id: int) -> None:
    response = await client.delete(
        f"{BASE_URL}/{subscription_id}",
        params={"client_id": settings.strava_client_id, "client_secret": settings.strava_client_secret},
    )
    response.raise_for_status()


async def create_subscription(client: httpx.AsyncClient, callback_url: str) -> dict:
    response = await client.post(
        BASE_URL,
        data={
            "client_id": settings.strava_client_id,
            "client_secret": settings.strava_client_secret,
            "callback_url": callback_url,
            "verify_token": settings.strava_verify_token,
        },
    )
    response.raise_for_status()
    return response.json()


async def main() -> None:
    parser = argparse.ArgumentParser(description="Manage Atlas' single Strava webhook subscription")
    parser.add_argument("action", choices=["list", "refresh"])
    parser.add_argument("--callback-url", default=f"{settings.backend_url}/webhooks/strava")
    args = parser.parse_args()

    async with httpx.AsyncClient(timeout=30) as client:
        existing = await list_subscriptions(client)
        if args.action == "list":
            print(existing)
            return
        for subscription in existing:
            await delete_subscription(client, subscription["id"])
        created = await create_subscription(client, args.callback_url)
        print(created)


if __name__ == "__main__":
    asyncio.run(main())
