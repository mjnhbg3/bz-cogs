import logging
from typing import Dict, List, Optional, Any
from openai import AsyncOpenAI
from redbot.core import Config
from redbot.core.bot import Red

logger = logging.getLogger("red.bz_cogs.aiuser")

class EndpointManager:
    """Manages multiple AI endpoints and their configurations"""
    
    def __init__(self, bot: Red, config: Config):
        self.bot = bot
        self.config = config
        self.clients: Dict[str, AsyncOpenAI] = {}
        
    async def get_client(self, endpoint: str) -> Optional[AsyncOpenAI]:
        """Get or create client for specified endpoint"""
        if endpoint in self.clients:
            return self.clients[endpoint]
            
        client = await self._create_client(endpoint)
        if client:
            self.clients[endpoint] = client
        return client
    
    async def _create_client(self, endpoint: str) -> Optional[AsyncOpenAI]:
        """Create a new client for the specified endpoint"""
        try:
            if endpoint == "openai":
                api_key = (await self.bot.get_shared_api_tokens("openai")).get("api_key")
                if not api_key:
                    logger.warning("OpenAI API key not found")
                    return None
                    
                return AsyncOpenAI(
                    api_key=api_key,
                    timeout=await self.config.openai_endpoint_request_timeout()
                )
                
            elif endpoint == "openrouter":
                api_key = (await self.bot.get_shared_api_tokens("openrouter")).get("api_key")
                if not api_key:
                    logger.warning("OpenRouter API key not found")
                    return None
                    
                return AsyncOpenAI(
                    api_key=api_key,
                    base_url="https://openrouter.ai/api/v1",
                    timeout=await self.config.openai_endpoint_request_timeout()
                )
                
            else:
                logger.warning(f"Unknown endpoint: {endpoint}")
                return None
                
        except Exception as e:
            logger.error(f"Failed to create client for {endpoint}: {e}")
            return None
    
    async def get_available_models(self) -> List[Dict[str, Any]]:
        """Get list of available regeneration models"""
        regen_models = await self.config.regen_models()
        available = []
        
        for model_config in regen_models:
            client = await self.get_client(model_config["endpoint"])
            if client:
                available.append(model_config)
                
        return available
    
    async def get_default_model(self) -> Optional[Dict[str, Any]]:
        """Get the default regeneration model"""
        regen_models = await self.config.regen_models()
        for model_config in regen_models:
            if model_config.get("default", False):
                client = await self.get_client(model_config["endpoint"])
                if client:
                    return model_config
        return None
    
    async def close_all_clients(self):
        """Close all endpoint clients"""
        for client in self.clients.values():
            if client:
                await client.close()
        self.clients.clear()