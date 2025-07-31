import logging
import random
from datetime import datetime, timezone

import discord
from discord import AllowedMentions
from redbot.core import Config, commands

from aiuser.messages_list.messages import MessagesList
from aiuser.response.chat.llm_pipeline import LLMPipeline
from aiuser.response.regeneration import add_subtle_regeneration, get_random_model
from aiuser.types.abc import MixinMeta
from aiuser.utils.response_utils import remove_patterns_from_response

logger = logging.getLogger("red.bz_cogs.aiuser")


async def should_reply(ctx: commands.Context) -> bool:
    if ctx.interaction:
        return False

    try:
        await ctx.fetch_message(ctx.message.id)
    except Exception:
        return False

    if (datetime.now(timezone.utc) - ctx.message.created_at).total_seconds() > 8 or random.random() < 0.25:
        return True

    async for last_msg in ctx.message.channel.history(limit=1):
        if last_msg.author == ctx.message.guild.me:
            return True
    return False

async def send_response(ctx: commands.Context, response: str, can_reply: bool, 
                      add_regeneration: bool = True, messages_list: MessagesList = None) -> discord.Message:
    allowed = AllowedMentions(everyone=False, roles=False, users=[ctx.message.author])
    message = None
    
    if len(response) >= 2000:
        for i in range(0, len(response), 2000):
            message = await ctx.send(response[i:i + 2000], allowed_mentions=allowed)
    elif can_reply and await should_reply(ctx):
        message = await ctx.message.reply(response, mention_author=False, allowed_mentions=allowed)
    elif ctx.interaction:
        message = await ctx.interaction.followup.send(response, allowed_mentions=allowed)
    else:
        message = await ctx.send(response, allowed_mentions=allowed)
    
    return message

async def create_chat_response(cog: MixinMeta, ctx: commands.Context, messages_list: MessagesList) -> bool:
    # Check if random model is enabled
    random_model_enabled = await cog.config.random_model_enabled()
    original_client = cog.openai_client
    selected_model_info = None
    
    try:
        # If random model is enabled, select a random model
        if random_model_enabled:
            random_model = await get_random_model(cog)
            if random_model:
                # Get client for the random model's endpoint
                client = await cog.endpoint_manager.get_client(random_model["endpoint"])
                if client:
                    cog.openai_client = client
                    messages_list.model = random_model["model"]
                    selected_model_info = random_model
                    logger.info(f"Using random model: {random_model['name']} via {random_model['endpoint']}")
        
        pipeline = LLMPipeline(cog, ctx, messages=messages_list)
        response = await pipeline.run()
        if not response:
            return False

        cleaned_response = await remove_patterns_from_response(ctx, cog.config, response)
        if not cleaned_response:
            return False

        # Send normal text response (back to original behavior)
        message = await send_response(ctx, cleaned_response, messages_list.can_reply)
        
        # Add subtle regeneration option and reaction monitoring
        await add_subtle_regeneration(cog, ctx, message, messages_list, selected_model_info)
        
        return True
        
    finally:
        # Restore original client
        cog.openai_client = original_client