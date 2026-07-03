"""AI Provider, Model, and Prompt repository."""

from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database.models.ai import AIProvider, AIModel, AIPrompt
from app.core.database.repositories.base import BaseRepository


class AIRepository(BaseRepository[AIProvider]):
    """Repository for AI models operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(AIProvider, session)
        self.model_session = session
        self.prompt_session = session

    async def get_active_providers(self) -> List[AIProvider]:
        """Get all active AI providers ordered by priority."""
        result = await self.session.execute(
            select(AIProvider)
            .where(AIProvider.is_active == True)
            .order_by(AIProvider.priority)
        )
        return list(result.scalars().all())

    async def get_primary_provider(self) -> Optional[AIProvider]:
        """Get the primary AI provider."""
        result = await self.session.execute(
            select(AIProvider).where(AIProvider.is_primary == True)
        )
        return result.scalar_one_or_none()

    async def get_provider_by_name(self, name: str) -> Optional[AIProvider]:
        """Get provider by name."""
        result = await self.session.execute(
            select(AIProvider).where(AIProvider.name == name)
        )
        return result.scalar_one_or_none()

    async def record_request(self, provider_id: int) -> None:
        """Record a successful AI request."""
        provider = await self.get(provider_id)
        if provider:
            await self.update(
                provider_id,
                {
                    "request_count": provider.request_count + 1,
                    "last_used": datetime.utcnow(),
                },
            )

    async def record_error(self, provider_id: int, error: str) -> None:
        """Record an AI request error."""
        provider = await self.get(provider_id)
        if provider:
            await self.update(
                provider_id,
                {
                    "error_count": provider.error_count + 1,
                    "last_error": error,
                },
            )

    async def get_model(self, model_id: int) -> Optional[AIModel]:
        """Get AI model by ID."""
        result = await self.model_session.execute(
            select(AIModel).where(AIModel.id == model_id)
        )
        return result.scalar_one_or_none()

    async def get_default_model(self) -> Optional[AIModel]:
        """Get the default AI model."""
        result = await self.model_session.execute(
            select(AIModel).where(AIModel.is_default == True)
        )
        return result.scalar_one_or_none()

    async def get_models_by_provider(self, provider_id: int) -> List[AIModel]:
        """Get all models for a provider."""
        result = await self.model_session.execute(
            select(AIModel)
            .where(AIModel.provider_id == provider_id)
            .where(AIModel.is_active == True)
        )
        return list(result.scalars().all())

    async def get_model_by_name(self, model_name: str) -> Optional[AIModel]:
        """Get model by name."""
        result = await self.model_session.execute(
            select(AIModel).where(AIModel.model_name == model_name)
        )
        return result.scalar_one_or_none()

    async def increment_model_usage(self, model_id: int) -> None:
        """Increment model usage count."""
        model = await self.get_model(model_id)
        if model:
            stmt = (
                update(AIModel)
                .where(AIModel.id == model_id)
                .values(usage_count=model.usage_count + 1)
            )
            await self.model_session.execute(stmt)
            await self.model_session.commit()

    async def get_prompt(self, name: str) -> Optional[AIPrompt]:
        """Get prompt template by name."""
        result = await self.prompt_session.execute(
            select(AIPrompt)
            .where(AIPrompt.name == name)
            .where(AIPrompt.is_active == True)
            .order_by(AIPrompt.version.desc())
        )
        return result.scalar_one_or_none()

    async def update_prompt(self, name: str, template: str) -> Optional[AIPrompt]:
        """Update or create prompt template."""
        existing = await self.get_prompt(name)
        if existing:
            new_version = existing.version + 1
            return await self.create(
                {
                    "name": name,
                    "template": template,
                    "version": new_version,
                    "is_active": True,
                }
            )
        else:
            return await self.create(
                {
                    "name": name,
                    "template": template,
                    "version": 1,
                    "is_active": True,
                }
            )

    async def get_prompt_history(self, name: str) -> List[AIPrompt]:
        """Get all versions of a prompt."""
        result = await self.prompt_session.execute(
            select(AIPrompt)
            .where(AIPrompt.name == name)
            .order_by(AIPrompt.version.desc())
        )
        return list(result.scalars().all())

    async def restore_prompt_version(self, prompt_id: int) -> Optional[AIPrompt]:
        """Restore a previous prompt version."""
        prompt = await self.get(prompt_id)
        if prompt:
            # Deactivate current versions
            current = await self.get_prompt(prompt.name)
            if current:
                await self.update(current.id, {"is_active": False})
            
            # Activate the selected version
            return await self.update(prompt_id, {"is_active": True})
        return None

    async def get_all_prompts(self) -> List[AIPrompt]:
        """Get all active prompts (latest versions)."""
        # Get distinct prompt names
        result = await self.prompt_session.execute(
            select(AIPrompt.name).distinct()
        )
        names = [row[0] for row in result.all()]
        
        # Get latest version of each
        prompts = []
        for name in names:
            prompt = await self.get_prompt(name)
            if prompt:
                prompts.append(prompt)
        
        return prompts

    async def get_ai_statistics(self) -> Dict[str, Any]:
        """Get AI usage statistics."""
        from sqlalchemy import func
        
        # Total requests
        total_requests_stmt = select(func.sum(AIProvider.request_count))
        total_requests_result = await self.session.execute(total_requests_stmt)
        total_requests = total_requests_result.scalar() or 0

        # Total errors
        total_errors_stmt = select(func.sum(AIProvider.error_count))
        total_errors_result = await self.session.execute(total_errors_stmt)
        total_errors = total_errors_result.scalar() or 0

        # Total model usage
        total_model_usage_stmt = select(func.sum(AIModel.usage_count))
        total_model_usage_result = await self.model_session.execute(total_model_usage_stmt)
        total_model_usage = total_model_usage_result.scalar() or 0

        return {
            "total_requests": total_requests,
            "total_errors": total_errors,
            "total_model_usage": total_model_usage,
        }
