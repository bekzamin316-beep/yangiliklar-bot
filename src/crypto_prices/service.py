"""Crypto Price API — CoinGecko + Binance fallback with in-memory cache."""

import asyncio
import logging
import time

import httpx

from src.core.config import settings

logger = logging.getLogger(__name__)

# CoinGecko ID → Binance symbol mapping
_BINANCE_SYMBOL_MAP = {
    "bitcoin": "BTCUSDT",
    "ethereum": "ETHUSDT",
    "solana": "SOLUSDT",
    "binancecoin": "BNBUSDT",
    "ripple": "XRPUSDT",
    "cardano": "ADAUSDT",
    "dogecoin": "DOGEUSDT",
    "tron": "TRXUSDT",
    "near": "NEARUSDT",
    "chainlink": "LINKUSDT",
    "polkadot": "DOTUSDT",
    "litecoin": "LTCUSDT",
    "avalanche-2": "AVAXUSDT",
    "polygon": "MATICUSDT",
    "aptos": "APTUSDT",
    "pepe": "1000PEPEUSDT",
    "shiba-inu": "1000SHIBUSDT",
}

# CoinGecko ID → CoinCap ID mapping
_COINCAP_MAP = {
    "bitcoin": "bitcoin",
    "ethereum": "ethereum",
    "solana": "solana",
    "binancecoin": "binance-coin",
    "ripple": "xrp",
    "cardano": "cardano",
    "dogecoin": "dogecoin",
    "tron": "tron",
    "near": "near-protocol",
    "chainlink": "chainlink",
    "polkadot": "polkadot",
    "litecoin": "litecoin",
    "avalanche-2": "avalanche",
    "polygon": "matic-network",
    "aptos": "aptos",
    "pepe": "pepe",
    "shiba-inu": "shiba-inu",
}

# Binance symbol → CoinGecko ID reverse mapping
_BINANCE_REVERSE_MAP = {v: k for k, v in _BINANCE_SYMBOL_MAP.items()}


class CryptoPriceService:
    """Fetch crypto prices with CoinGecko primary + Binance fallback + cache."""

    COINGECKO_URL = "https://api.coingecko.com/api/v3"
    BINANCE_URL = "https://api.binance.com/api/v3"

    # In-memory cache
    _cache: dict = {}
    _cache_ts: float = 0.0
    _cache_ttl: int = 30  # seconds — reuse data if fresh enough

    def __init__(self):
        self.api_key = settings.coingecko_api_key or None
        self.timeout = 15

    async def fetch_prices(self, coin_ids: list[str], vs_currency: str = "usd") -> dict:
        """Fetch prices: cache → CoinGecko → Binance fallback.

        Returns dict mapping coin_id → {'price': float, 'change_24h': float}
        """
        if not coin_ids:
            return {}

        # Return cache if still fresh
        now = time.monotonic()
        if self._cache and (now - self._cache_ts) < self._cache_ttl:
            cached = {k: v for k, v in self._cache.items() if k in coin_ids}
            if len(cached) == len(coin_ids):
                logger.debug("Using cached prices (age=%.1fs)", now - self._cache_ts)
                return cached

        # Try CoinGecko first
        result = await self._fetch_coingecko(coin_ids, vs_currency)
        if result:
            self._cache = result
            self._cache_ts = now
            return result

        # CoinGecko failed → Binance fallback
        logger.info("CoinGecko failed, falling back to Binance API")
        result = await self._fetch_binance(coin_ids)
        if result:
            self._cache = result
            self._cache_ts = now
            return result

        # Both failed → CoinCap fallback
        logger.info("Binance failed, falling back to CoinCap API")
        result = await self._fetch_coincap(coin_ids)
        if result:
            self._cache = result
            self._cache_ts = now
            return result

        # Both failed → return stale cache if available
        if self._cache:
            logger.warning("All APIs failed — using stale cache (age=%.1fs)", now - self._cache_ts)
            return {k: v for k, v in self._cache.items() if k in coin_ids}

        logger.error("No price data available (no cache, all APIs failed)")
        return {}

    async def _fetch_coingecko(self, coin_ids: list[str], vs_currency: str = "usd") -> dict:
        """Fetch from CoinGecko. Returns empty dict on any failure."""
        params = {
            "ids": ",".join(coin_ids),
            "vs_currencies": vs_currency,
            "include_24hr_change": "true",
            "include_24hr_high": "false",
            "include_24hr_low": "false",
        }
        headers = {}
        if self.api_key:
            headers["x-cg-demo-api-key"] = self.api_key

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout)) as client:
                resp = await client.get(
                    f"{self.COINGECKO_URL}/simple/price",
                    params=params,
                    headers=headers,
                )
                if resp.status_code == 429:
                    logger.warning("CoinGecko rate limited (429) — will use fallback")
                    return {}
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

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                logger.warning("CoinGecko rate limited (429)")
                return {}
            logger.error("CoinGecko HTTP error: %s", e)
            return {}
        except Exception as e:
            logger.error("CoinGecko fetch failed: %s", e)
            return {}

    async def _fetch_coincap(self, coin_ids: list[str]) -> dict:
        """Fetch from CoinCap API (free, no key, no regional blocks)."""
        result = {}
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout)) as client:
                for coin_id in coin_ids:
                    coincap_id = _COINCAP_MAP.get(coin_id, coin_id)
                    resp = await client.get(
                        f"https://api.coincap.io/v2/assets/{coincap_id}",
                    )
                    if resp.status_code != 200:
                        logger.warning("CoinCap %s returned %d", coincap_id, resp.status_code)
                        continue
                    data = resp.json().get("data", {})
                    if data:
                        result[coin_id] = {
                            "price": float(data.get("priceUsd", 0)),
                            "change_24h": float(data.get("changePercent24Hr", 0)),
                        }
                return result

        except Exception as e:
            logger.error("CoinCap fetch failed: %s", e)
            return {}

    async def _fetch_binance(self, coin_ids: list[str]) -> dict:
        """Fetch from Binance API as fallback. Returns empty dict on failure."""
        symbols = []
        for coin_id in coin_ids:
            sym = _BINANCE_SYMBOL_MAP.get(coin_id)
            if sym:
                symbols.append(sym)

        if not symbols:
            logger.warning("No Binance symbols found for coin_ids: %s", coin_ids)
            return {}

        result = {}
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout)) as client:
                for symbol in symbols:
                    resp = await client.get(
                        f"{self.BINANCE_URL}/ticker/24hr",
                        params={"symbol": symbol},
                    )
                    if resp.status_code != 200:
                        logger.warning("Binance %s returned %d", symbol, resp.status_code)
                        continue
                    data = resp.json()

                    coin_id = _BINANCE_REVERSE_MAP.get(symbol)
                    if coin_id:
                        price = float(data.get("lastPrice", 0))
                        change = float(data.get("priceChangePercent", 0))
                        result[coin_id] = {
                            "price": price,
                            "change_24h": change,
                        }

                return result

        except Exception as e:
            logger.error("Binance fetch failed: %s", e)
            return {}

    async def get_coin_ids(self) -> list[str]:
        """Get list of supported coin IDs."""
        headers = {}
        if self.api_key:
            headers["x-cg-demo-api-key"] = self.api_key

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout)) as client:
                resp = await client.get(
                    f"{self.COINGECKO_URL}/coins/list",
                    params={"per_page": 50, "page": 1},
                    headers=headers,
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
            return f"${price:,.2f}"
        elif price >= 0.01:
            return f"${price:.4f}"
        else:
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
    coin_ids = ["bitcoin", "ethereum", "solana", "binancecoin", "ripple"]

    prices = await service.fetch_prices(coin_ids)
    for coin_id, data in prices.items():
        print(
            f"{service.get_display_name(coin_id):12} "
            f"{service.format_price(data['price'], coin_id):>15} "
            f"{service.format_change(data['change_24h'])}"
        )


if __name__ == "__main__":
    asyncio.run(main())
