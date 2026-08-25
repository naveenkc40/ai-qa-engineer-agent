import asyncio
from pathlib import Path

from dotenv import load_dotenv

from agents.application_discovery_agent import (
    ApplicationDiscoveryAgent
)


load_dotenv()


async def main():

    base_dir = Path(__file__).resolve().parent.parent

    storage_state = (
        base_dir
        / "application_context"
        / "storage_state.json"
    )

    base_url = "https://www.saucedemo.com"

    print(f"Storage state: {storage_state}")
    print(f"Exists: {storage_state.exists()}")

    if not storage_state.exists():
        raise FileNotFoundError(
            f"Storage state not found: {storage_state}"
        )

    agent = ApplicationDiscoveryAgent(
        base_url=base_url,
        storage_state=str(storage_state)
    )
    discovery = (
        await agent.discover_authenticated()
    )

    agent.save_authenticated(
        discovery
    )

    print("\n")
    print("=" * 60)
    print("AUTHENTICATED DISCOVERY COMPLETE")
    print("=" * 60)

    print(
        f"\nProducts: "
        f"{len(discovery['products'])}"
    )

    print(
        f"Cart URL: "
        f"{discovery['cart']['href']}"
    )

    print(
        f"Buttons: "
        f"{len(discovery['buttons'])}"
    )

    print(
        f"Links: "
        f"{len(discovery['links'])}"
    )


if __name__ == "__main__":
    asyncio.run(main())
