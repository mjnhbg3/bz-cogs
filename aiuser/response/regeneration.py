import logging
import random
from typing import Dict, List, Optional, Any
import discord
from redbot.core import commands, Config
from redbot.core.bot import Red

from aiuser.messages_list.messages import MessagesList, create_messages_list
from aiuser.response.chat.llm_pipeline import LLMPipeline
from aiuser.types.abc import MixinMeta
from aiuser.utils.endpoint_manager import EndpointManager
from aiuser.utils.response_rating import ResponseRating
from aiuser.utils.response_utils import remove_patterns_from_response

logger = logging.getLogger("red.bz_cogs.aiuser")

# Mapping of Discord reactions to sentiment ratings
REACTION_SENTIMENT_MAP = {
    "👍": "positive",
    "👎": "negative", 
    "❤️": "love",
    "😂": "funny",
    "😮": "surprising",
    "😢": "sad",
    "😡": "angry",
    "🤔": "thoughtful",
    "🎯": "accurate", 
    "❓": "confusing"
}

class SubtleRegenerationView(discord.ui.View):
    """Minimal, unobtrusive regeneration UI"""
    
    def __init__(self, cog: MixinMeta, ctx: commands.Context, original_message: discord.Message, 
                 messages_list: MessagesList, selected_model_info: Dict = None, timeout: float = 1800):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.ctx = ctx
        self.original_message = original_message
        self.messages_list = messages_list
        self.selected_model_info = selected_model_info
        self.endpoint_manager = EndpointManager(cog.bot, cog.config)
        self.rating_system = ResponseRating(cog.config)
        
        # Add a small, subtle regeneration button
        self.add_item(RegenerateButton(self))
    
    async def on_timeout(self):
        """Called when the view times out"""
        for item in self.children:
            item.disabled = True
        try:
            await self.original_message.edit(view=self)
        except (discord.NotFound, discord.HTTPException):
            pass

class RegenerateButton(discord.ui.Button):
    """Small, subtle regenerate button"""
    
    def __init__(self, parent_view: SubtleRegenerationView):
        self.parent_view = parent_view
        super().__init__(
            style=discord.ButtonStyle.secondary,
            emoji="🔄",
            label="Try different model",
            row=0
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Handle regeneration request"""
        # Show dropdown for model selection
        available_models = await self.parent_view.endpoint_manager.get_available_models()
        
        if not available_models:
            await interaction.response.send_message("❌ No alternative models available", ephemeral=True)
            return
        
        if len(available_models) == 1:
            # Only one model available, just regenerate with it
            await self._regenerate_with_model(available_models[0], interaction)
        else:
            # Show selection dropdown
            view = ModelSelectionView(self.parent_view, available_models)
            await interaction.response.send_message("Choose a model:", view=view, ephemeral=True)

    async def _regenerate_with_model(self, model_config: Dict[str, Any], interaction: discord.Interaction):
        """Actually regenerate with the specified model"""
        try:
            # Get the appropriate client for this endpoint
            client = await self.parent_view.endpoint_manager.get_client(model_config["endpoint"])
            if not client:
                await interaction.followup.send("❌ Failed to connect to endpoint", ephemeral=True)
                return
            
            # Create a temporary pipeline with the new model
            temp_messages = MessagesList(
                self.parent_view.messages_list.ctx,
                self.parent_view.messages_list.author,
                self.parent_view.messages_list.channel_id,
                self.parent_view.messages_list.guild_id,
                model_config["model"],
                self.parent_view.messages_list.can_reply,
                self.parent_view.messages_list.messages,
                self.parent_view.messages_list.conversation_mode
            )
            
            # Set the client for this endpoint
            original_client = self.parent_view.cog.openai_client
            self.parent_view.cog.openai_client = client
            
            try:
                pipeline = LLMPipeline(self.parent_view.cog, self.parent_view.ctx, temp_messages)
                await pipeline.setup_tools()
                response = await pipeline.generate_response()
                
                if response:
                    # Clean the response
                    cleaned_response = await remove_patterns_from_response(
                        self.parent_view.ctx, self.parent_view.cog.config, response
                    )
                    
                    # Update the original message with new response
                    model_attribution = f"\n\n*— {model_config['name']}*"
                    new_content = cleaned_response + model_attribution
                    
                    # Truncate if too long
                    if len(new_content) > 2000:
                        new_content = cleaned_response[:1950] + "..." + model_attribution
                    
                    await self.parent_view.original_message.edit(content=new_content)
                    
                    # Update the selected model info
                    self.parent_view.selected_model_info = model_config
                    
                    if not interaction.response.is_done():
                        await interaction.response.send_message(f"✅ Regenerated with {model_config['name']}", ephemeral=True)
                    else:
                        await interaction.followup.send(f"✅ Regenerated with {model_config['name']}", ephemeral=True)
                else:
                    if not interaction.response.is_done():
                        await interaction.response.send_message("❌ Failed to generate response", ephemeral=True)
                    else:
                        await interaction.followup.send("❌ Failed to generate response", ephemeral=True)
                    
            finally:
                # Restore original client
                self.parent_view.cog.openai_client = original_client
                
        except Exception as e:
            logger.error(f"Failed to regenerate response: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ An error occurred during regeneration", ephemeral=True)
            else:
                await interaction.followup.send("❌ An error occurred during regeneration", ephemeral=True)

class ModelSelectionView(discord.ui.View):
    """Ephemeral view for model selection"""
    
    def __init__(self, parent_view: SubtleRegenerationView, available_models: List[Dict]):
        super().__init__(timeout=60)
        self.parent_view = parent_view
        self.add_item(ModelSelectionDropdown(self, available_models))

class ModelSelectionDropdown(discord.ui.Select):
    """Dropdown for selecting regeneration model"""
    
    def __init__(self, parent_view: ModelSelectionView, available_models: List[Dict]):
        self.parent_view = parent_view
        self.available_models = available_models
        
        options = []
        for model in available_models:
            emoji = "⭐" if model.get("default", False) else "🤖"
            options.append(discord.SelectOption(
                label=model["name"],
                value=model["name"],
                description=f"Via {model['endpoint']}",
                emoji=emoji
            ))
        
        super().__init__(
            placeholder="Choose a model...",
            min_values=1,
            max_values=1,
            options=options
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Handle model selection"""
        selected_name = self.values[0]
        selected_model = None
        
        for model in self.available_models:
            if model["name"] == selected_name:
                selected_model = model
                break
        
        if selected_model:
            # Get the regenerate button from the original view
            regen_button = self.parent_view.parent_view.children[0]
            await regen_button._regenerate_with_model(selected_model, interaction)
        else:
            await interaction.response.send_message("❌ Model not found", ephemeral=True)

async def add_subtle_regeneration(cog: MixinMeta, ctx: commands.Context, 
                                message: discord.Message, messages_list: MessagesList, 
                                selected_model_info: Dict = None) -> discord.Message:
    """Add subtle regeneration controls and reaction monitoring to a message"""
    try:
        # Add the subtle regeneration view (small button)
        view = SubtleRegenerationView(cog, ctx, message, messages_list, selected_model_info)
        await message.edit(view=view)
        
        # Set up reaction monitoring for sentiment tracking
        await setup_reaction_monitoring(cog, message, selected_model_info)
        
        return message
        
    except Exception as e:
        logger.error(f"Failed to add subtle regeneration: {e}")
        return message

async def setup_reaction_monitoring(cog: MixinMeta, message: discord.Message, 
                                   selected_model_info: Dict = None):
    """Set up monitoring for Discord reactions to track sentiment"""
    try:
        # Store message info for reaction tracking
        rating_system = ResponseRating(cog.config)
        
        # Store the message info in bot's memory for reaction tracking
        if not hasattr(cog, 'tracked_messages'):
            cog.tracked_messages = {}
        
        model_name = "Unknown"
        endpoint_name = "Unknown"
        
        if selected_model_info:
            model_name = selected_model_info.get("name", "Unknown")
            endpoint_name = selected_model_info.get("endpoint", "Unknown")
        else:
            # Try to get default model info
            default_model = await cog.endpoint_manager.get_default_model()
            if default_model:
                model_name = default_model.get("name", "Unknown")
                endpoint_name = default_model.get("endpoint", "Unknown")
        
        cog.tracked_messages[message.id] = {
            "model": model_name,
            "endpoint": endpoint_name,
            "content": message.content[:500] if message.content else None,
            "guild_id": message.guild.id,
            "rating_system": rating_system
        }
        
        logger.debug(f"Set up reaction monitoring for message {message.id}")
        
    except Exception as e:
        logger.error(f"Failed to set up reaction monitoring: {e}")

async def handle_reaction_add(cog: MixinMeta, payload: discord.RawReactionActionEvent):
    """Handle reaction additions for sentiment tracking"""
    try:
        if not hasattr(cog, 'tracked_messages'):
            return
        
        message_id = payload.message_id
        if message_id not in cog.tracked_messages:
            return
        
        # Skip bot reactions
        if payload.user_id == cog.bot.user.id:
            return
        
        emoji_str = str(payload.emoji)
        if emoji_str not in REACTION_SENTIMENT_MAP:
            return
        
        message_info = cog.tracked_messages[message_id]
        sentiment = REACTION_SENTIMENT_MAP[emoji_str]
        
        # Log the reaction as a rating
        rating_key = f"{message_id}_{payload.user_id}_{emoji_str}"
        await message_info["rating_system"].log_rating(
            message_id=rating_key,
            user_id=payload.user_id,
            guild_id=message_info["guild_id"],
            model=message_info["model"],
            endpoint=message_info["endpoint"],
            rating=sentiment,
            response_content=message_info["content"]
        )
        
        logger.debug(f"Logged reaction {emoji_str} ({sentiment}) from user {payload.user_id} on message {message_id}")
        
    except Exception as e:
        logger.error(f"Failed to handle reaction: {e}")

async def get_random_model(cog: MixinMeta) -> Optional[Dict[str, Any]]:
    """Get a random model from available regeneration models"""
    try:
        endpoint_manager = EndpointManager(cog.bot, cog.config)
        available_models = await endpoint_manager.get_available_models()
        
        if available_models:
            return random.choice(available_models)
        return None
        
    except Exception as e:
        logger.error(f"Failed to get random model: {e}")
        return None