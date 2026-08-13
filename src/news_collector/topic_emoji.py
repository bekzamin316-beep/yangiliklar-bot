"""Topic-based emoji picker for Telegram news headlines."""

TOPIC_RULES: list[tuple[str, str, tuple[str, ...]]] = [
    ("bitcoin", "🟠", ("bitcoin", "btc", "halving")),
    ("ethereum", "🔷", ("ethereum", "eth", "ether", "layer 2", "l2")),
    ("sec", "🏛️", ("sec", "securities and exchange", "lawsuit", "court", "fines")),
    ("regulation", "⚖️", ("regulation", "regulatory", "legislation", "law", "prosecut")),
    ("etf", "🏦", ("etf", "exchange-traded fund")),
    ("exchange", "💱", ("binance", "coinbase", "kraken", "okx", "bybit", "exchange", "listing", "delist")),
    ("defi", "🔗", ("defi", "decentralized finance", "liquidity", "yield", "lending")),
    ("nft", "🎨", ("nft", "non-fungible", "digital art", "collectible")),
    ("mining", "⛏️", ("mining", "miner", "hashrate", "hash rate", "asic", "proof-of-work", "pow")),
    ("staking", "🏦", ("staking", "stake", "validator")),
    ("airdrop", "🎁", ("airdrop", "reward", "incentive")),
    ("hack", "🛡️", ("hack", "breach", "exploit", "vulnerab", "theft", "stolen", "attack", "phish")),
    ("stablecoin", "💵", ("stablecoin", "tether", "usdt", "usdc", "dai")),
    ("price", "📈", ("price", "market", "rally", "surge", "plunge", "crash", "record high", "all-time")),
    ("macro", "🌍", ("fed", "federal reserve", "inflation", "interest rate", "econom", "gdp", "recession")),
    ("onchain", "🔍", ("on-chain", "onchain", "wallet", "address", "whale", "transaction", "transfer")),
    ("metaverse", "🕶️", ("metaverse", "virtual world", "virtual reality")),
    ("crypto", "🪙", ("crypto", "cryptocurrency", "token", "coin", "altcoin", "blockchain", "web3")),
]


def get_topic_emoji(title: str = "", tags: str | list = "", summary: str = "") -> str:
    """Pick a Telegram-friendly emoji matching the news topic.

    Rules are checked in priority order against tags, then title, then summary.
    Falls back to a generic crypto emoji when no topic matches.
    """
    if isinstance(tags, list):
        tag_text = " ".join(tags).lower()
    else:
        tag_text = str(tags or "").lower()

    haystack = " ".join([tag_text, str(title or "").lower(), str(summary or "").lower()])

    for _label, emoji, keywords in TOPIC_RULES:
        for kw in keywords:
            if kw in haystack:
                return emoji

    return "🪙"