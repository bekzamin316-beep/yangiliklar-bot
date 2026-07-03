"""News processing service."""

from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database.repositories.news_repository import NewsRepository
from app.ai.services.fallback_service import FallbackAIService
import logging
import json

logger = logging.getLogger(__name__)


class NewsProcessor:
    """Processes news items through AI analysis and publishing."""

    def __init__(
        self,
        db_session: AsyncSession,
        ai_service: FallbackAIService,
        importance_threshold: int = 50
    ):
        self.db_session = db_session
        self.news_repo = NewsRepository(db_session)
        self.ai_service = ai_service
        self.importance_threshold = importance_threshold

    async def process_news(
        self,
        title: str,
        summary: str,
        source_name: str,
        source_url: str,
        content_hash: str
    ) -> Optional[Dict[str, Any]]:
        """Process a single news item through AI analysis."""
        
        # Check for duplicates
        existing = await self.news_repo.get_by_hash(content_hash)
        if existing:
            logger.info(f"Duplicate news detected: {title}")
            return None
        
        # Analyze with AI
        try:
            analysis = await self.ai_service.analyze_news(
                title=title,
                content=summary,
                source=source_name
            )
            
            if not analysis:
                logger.warning(f"AI analysis failed for: {title}")
                return None
            
            importance_score = analysis.get('importance_score', 0)
            
            # Filter by importance
            if importance_score < self.importance_threshold:
                logger.info(f"News importance too low ({importance_score}): {title}")
                return None
            
            # Store in database
            news_data = {
                'title': title,
                'summary': analysis.get('summary', summary),
                'analysis': analysis.get('analysis', ''),
                'source_name': source_name,
                'source_url': source_url,
                'content_hash': content_hash,
                'sentiment': analysis.get('sentiment', 'neutral'),
                'importance_score': importance_score,
                'tags': json.dumps(analysis.get('tags', []))
            }
            
            news = await self.news_repo.create(news_data)
            
            logger.info(f"News processed successfully: {title} (importance: {importance_score})")
            
            return {
                'id': news.id,
                'title': title,
                'summary': news_data['summary'],
                'analysis': news_data['analysis'],
                'sentiment': news_data['sentiment'],
                'importance_score': importance_score,
                'source_url': source_url
            }
            
        except Exception as e:
            logger.error(f"Error processing news: {e}")
            return None

    async def format_post(self, news_data: Dict[str, Any]) -> str:
        """Format news for Telegram post."""
        sentiment_emoji = {
            'bullish': '🟢',
            'bearish': '🔴',
            'neutral': '⚪'
        }.get(news_data['sentiment'].lower(), '⚪')
        
        sentiment_text = {
            'bullish': 'Bullish',
            'bearish': 'Bearish',
            'neutral': 'Neutral'
        }.get(news_data['sentiment'].lower(), 'Neutral')
        
        post = f"""🚨 KRIPTO YANGILIK

📰 Yangilik:

{news_data['summary']}

🤖 AI Tahlili:

{news_data['analysis']}

📊 Kayfiyat:

{sentiment_text} {sentiment_emoji}

⭐ Muhimlik:

{news_data['importance_score']}/10

🔗 Manba:

{news_data['source_url']}

#Crypto #Bitcoin"""
        
        return post
