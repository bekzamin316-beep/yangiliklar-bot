"""Result of AI analysis of a single news article."""

from dataclasses import dataclass


@dataclass
class NewsAnalysis:
    """AI-generated analysis of a news article."""

    title_uz: str = ""             # Uzbek translation of the news title
    summary_uz: str = ""           # Uzbek summary
    analysis_uz: str = ""          # Detailed news description in Uzbek (factual, no personal opinion)
    importance_score: int = 0      # 0-100
    sentiment: str = "neutral"     # bullish / bearish / neutral
    tags: list[str] = None         # Relevant crypto tags

    def __post_init__(self):
        if self.tags is None:
            self.tags = []
