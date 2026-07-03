"""Scheduler jobs for news collection and digest."""

import asyncio
from datetime import datetime, time
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from aiogram import Bot
import logging

from app.core.config import settings
from app.rss.collector import RSSCollector
from app.ai.services.fallback_service import FallbackAIService
from app.news.processor import NewsProcessor
from app.core.database.repositories.news_repository import NewsRepository
from app.core.database.repositories.settings_repository import SettingsRepository

logger = logging.getLogger(__name__)


class NewsScheduler:
    """Handles scheduled news collection tasks."""

    def __init__(
        self,
        db_session_factory,
        bot: Bot,
        ai_service: FallbackAIService
    ):
        self.db_session_factory = db_session_factory
        self.bot = bot
        self.ai_service = ai_service
        self.rss_collector = RSSCollector()

    async def collect_and_publish_news(self):
        """Collect news from RSS feeds and publish to Telegram."""
        async with self.db_session_factory() as session:
            try:
                # Get RSS sources from database or config
                settings_repo = SettingsRepository(session)
                rss_sources = await settings_repo.get_rss_sources()
                
                if not rss_sources:
                    # Fallback to config
                    rss_urls = settings.rss_source_list
                    rss_sources = [
                        {'url': url, 'name': url.split('//')[-1].split('/')[0]}
                        for url in rss_urls
                    ]
                
                logger.info(f"Collecting news from {len(rss_sources)} sources")
                
                # Collect news
                news_items = await self.rss_collector.collect_from_urls(
                    [s['url'] for s in rss_sources]
                )
                
                logger.info(f"Collected {len(news_items)} news items")
                
                # Process each news item
                processor = NewsProcessor(
                    db_session=session,
                    ai_service=self.ai_service,
                    importance_threshold=settings.IMPORTANCE_THRESHOLD
                )
                
                published_count = 0
                for item in news_items[:10]:  # Limit processing to 10 items per run
                    result = await processor.process_news(
                        title=item.title,
                        summary=item.summary,
                        source_name=item.source_name,
                        source_url=item.link,
                        content_hash=item.content_hash
                    )
                    
                    if result:
                        # Format and send to Telegram
                        post_text = await processor.format_post(result)
                        
                        try:
                            message = await self.bot.send_message(
                                chat_id=settings.TELEGRAM_CHANNEL_ID,
                                text=post_text,
                                disable_web_page_preview=False
                            )
                            
                            # Update news with telegram info
                            news_repo = NewsRepository(session)
                            await news_repo.update_telegram_info(
                                result['id'],
                                message.message_id,
                                f"https://t.me/{settings.TELEGRAM_CHANNEL_ID}/{message.message_id}"
                            )
                            
                            published_count += 1
                            logger.info(f"Published news: {item.title}")
                            
                        except Exception as e:
                            logger.error(f"Failed to publish to Telegram: {e}")
                
                logger.info(f"Published {published_count} news items")
                
                await session.commit()
                
            except Exception as e:
                logger.error(f"Error in news collection job: {e}")
                await session.rollback()
            finally:
                await self.rss_collector.close()

    async def generate_daily_digest(self):
        """Generate and send daily digest."""
        async with self.db_session_factory() as session:
            try:
                logger.info("Generating daily digest")
                
                news_repo = NewsRepository(session)
                
                # Get today's top news
                today_news = await news_repo.get_top_news(
                    limit=10,
                    min_importance=60
                )
                
                if not today_news:
                    logger.info("No news for digest today")
                    return
                
                # Generate digest with AI
                digest_content = await self.ai_service.generate_digest(today_news)
                
                # Send to Telegram
                await self.bot.send_message(
                    chat_id=settings.TELEGRAM_CHANNEL_ID,
                    text=digest_content,
                    disable_web_page_preview=False
                )
                
                logger.info("Daily digest sent successfully")
                
                await session.commit()
                
            except Exception as e:
                logger.error(f"Error generating digest: {e}")
                await session.rollback()


async def run_news_collection(scheduler: NewsScheduler):
    """Run news collection job."""
    await scheduler.collect_and_publish_news()


async def run_daily_digest(scheduler: NewsScheduler):
    """Run daily digest job."""
    await scheduler.generate_daily_digest()
