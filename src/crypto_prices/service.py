"""Crypto Price API — CoinGecko integration."""

import asyncio
import logging
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)


class CryptoPriceService:
    """Fetch cryptocurrency prices from CoinGecko API."""

    BASE_URL = "https://api.coingecko.com/api/v3"

    def __init__(self):
        self.api_key = None  # CoinGecko free tier doesn't require API key
        self.timeout = 15

    async def fetch_prices(self, coin_ids: list[str], vs_currency: str = "usd") -> dict:
        """Fetch current prices for multiple coins.

        Args:
            coin_ids: List of CoinGecko coin IDs (e.g., 'bitcoin', 'ethereum', 'solana')
            vs_currency: Currency to price in (default 'usd')

        Returns:
            Dict mapping coin_id -> {'price': float, 'change_24h': float}
        """
        if not coin_ids:
            return {}

        params = {
            "ids": ",".join(coin_ids),
            "vs_currencies": vs_currency,
            "include_24hr_change": "true",
            "include_24hr_high": "false",
            "include_24hr_low": "false",
        }

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout)) as client:
                resp = await client.get(
                    f"{self.BASE_URL}/simple/price",
                    params=params,
                )
                resp.raise_for_status()
                data = resp.json()

                result = {}
                for coin_id in coin_ids:
                    if coin_id in data:
                        coin_data = data[coin_id]
                        result[coin_id] = {
                            "price": coin_data.get(vs_currency, 0),
                            "change_24h": coin_data.get(f"{vs_currency}_24h_change", 0),
                        }
                return result

        except Exception as e:
            logger.error("Failed to fetch crypto prices: %s", e)
            return {}

    async def get_coin_ids(self) -> list[str]:
        """Get list of supported coin IDs."""
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout)) as client:
                resp = await client.get(
                    f"{self.BASE_URL}/coins/list",
                    params={"per_page": 50, "page": 1},
                )
                resp.raise_for_status()
                coins = resp.json()
                return [c["id"] for c in coins]
        except Exception as e:
            logger.error("Failed to get coin list: %s", e)
            return []

    @staticmethod
    def format_price(price: float, coin_id: str) -> str:
        """Format price for display."""
        if coin_id in ["bitcoin", "ethereum", "avalanche-2", "matic-network"]:
            # >= $1 coins — show 2 decimal places
            return f"${price:,.2f}"
        elif price >= 0.01:
            # $0.01-$0.99 — show 4 decimal places
            return f"${price:.4f}"
        else:
            # < $0.01 — show scientific notation
            return f"${price:.8f}"

    @staticmethod
    def format_change(change: float) -> str:
        """Format 24h change with colored indicator."""
        if change > 0:
            return f"🟩 +{change:.2f}%"
        elif change < 0:
            return f"🟥 {change:.2f}%"
        else:
            return "⬜ 0.00%"

    @staticmethod
    def get_display_name(coin_id: str) -> str:
        """Get short display name for coin ID."""
        names = {
            "bitcoin": "Btc",
            "ethereum": "Eth",
            "solana": "Sol",
            "binancecoin": "BNB",
            "ripple": "XRP",
            "cardano": "Ada",
            "avalanche-2": "Avax",
            "polygon": "Matic",
            "dogecoin": "Doge",
            "tron": "Trx",
            "near": "Near",
            "chainlink": "Link",
            "polkadot": "Dot",
            "aptos": "Apt",
            "Celestia": "Tia",
            "litecoin": "Ltc",
            "pepe": "Pepe",
            "shiba-inu": "Shib",
        }
        return names.get(coin_id, coin_id.title())


async def main():
    """Test the price service."""
    service = CryptoPriceService()

    # Default coins to track
    coin_ids = [
        "bitcoin",
        "ethereum",
        "solana",
        "binancecoin",
        "ripple",
    ]

    prices = await service.fetch_prices(coin_ids)
    for coin_id, data in prices.items():
        print(
            f"{service.get_display_name(coin_id):12} "
            f"{service.format_price(data['price'], coin_id):>15} "
            f"{service.format_change(data['change_24h'])}"
        )


if __name__ == "__main__":
    asyncio.run(main())