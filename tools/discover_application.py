import asyncio
import os

from dotenv import load_dotenv

from agents.application_discovery_agent import (
    ApplicationDiscoveryAgent
)


async def main():

    load_dotenv()

    base_url = os.getenv(
        "QA_APP_URL"
    )

    if not base_url:
        raise ValueError(
            "QA_APP_URL is missing from .env"
        )

    agent = ApplicationDiscoveryAgent(
        base_url
    )

    discovery = await agent.discover()

    agent.save(discovery)

    print("\n")
    print("=" * 60)
    print("APPLICATION DISCOVERY COMPLETE")
    print("=" * 60)

    print(
        f"\nApplication: "
        f"{discovery['application']}"
    )

    print(
        f"Title: "
        f"{discovery['page']['title']}"
    )

    print(
        f"URL: "
        f"{discovery['page']['url']}"
    )

    print(
        f"\nLinks discovered: "
        f"{len(discovery['links'])}"
    )

    print(
        f"Buttons discovered: "
        f"{len(discovery['buttons'])}"
    )


if __name__ == "__main__":
    asyncio.run(main())