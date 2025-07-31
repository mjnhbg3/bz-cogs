import json
import logging
from typing import List, Dict, Any

import discord
from redbot.core import checks, commands
from redbot.core.utils.chat_formatting import box, pagify

from aiuser.types.abc import MixinMeta

logger = logging.getLogger("red.bz_cogs.aiuser")

class RegenerationSettings(MixinMeta):
    """Settings for response regeneration and model management"""
    
    @commands.group()
    @checks.admin_or_permissions(manage_guild=True)
    async def regen(self, ctx):
        """Manage response regeneration settings"""
        pass
    
    @regen.command(name="models")
    async def regen_models_list(self, ctx):
        """List available regeneration models"""
        try:
            regen_models = await self.config.regen_models()
            
            if not regen_models:
                await ctx.send("No regeneration models configured.")
                return
            
            embed = discord.Embed(
                title="Regeneration Models",
                color=discord.Color.blue()
            )
            
            for i, model in enumerate(regen_models, 1):
                name = model.get("name", "Unknown")
                model_id = model.get("model", "Unknown")
                endpoint = model.get("endpoint", "Unknown")
                is_default = "⭐ Default" if model.get("default", False) else ""
                
                embed.add_field(
                    name=f"{i}. {name} {is_default}",
                    value=f"**Model:** {model_id}\n**Endpoint:** {endpoint}",
                    inline=False
                )
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Failed to list regeneration models: {e}")
            await ctx.send("❌ Failed to retrieve regeneration models.")
    
    @regen.command(name="add")
    async def regen_add_model(self, ctx, name: str, model: str, endpoint: str, default: bool = False):
        """Add a new regeneration model
        
        Parameters:
        - name: Display name for the model
        - model: Model identifier (e.g., gpt-4.1, anthropic/claude-3.5-sonnet)
        - endpoint: API endpoint (openai, openrouter)
        - default: Whether this should be the default model (True/False)
        """
        try:
            if endpoint not in ["openai", "openrouter"]:
                await ctx.send("❌ Endpoint must be either 'openai' or 'openrouter'")
                return
            
            regen_models = await self.config.regen_models()
            
            # Check if model with same name already exists
            for existing_model in regen_models:
                if existing_model.get("name", "").lower() == name.lower():
                    await ctx.send(f"❌ Model with name '{name}' already exists.")
                    return
            
            # If this is set as default, remove default from others
            if default:
                for model_config in regen_models:
                    model_config["default"] = False
            
            # Add new model
            new_model = {
                "name": name,
                "model": model,
                "endpoint": endpoint,
                "default": default
            }
            
            regen_models.append(new_model)
            await self.config.regen_models.set(regen_models)
            
            default_text = " (set as default)" if default else ""
            await ctx.send(f"✅ Added regeneration model '{name}'{default_text}")
            
        except Exception as e:
            logger.error(f"Failed to add regeneration model: {e}")
            await ctx.send("❌ Failed to add regeneration model.")
    
    @regen.command(name="remove")
    async def regen_remove_model(self, ctx, name: str):
        """Remove a regeneration model by name"""
        try:
            regen_models = await self.config.regen_models()
            
            # Find and remove the model
            model_found = False
            for i, model in enumerate(regen_models):
                if model.get("name", "").lower() == name.lower():
                    removed_model = regen_models.pop(i)
                    model_found = True
                    break
            
            if not model_found:
                await ctx.send(f"❌ Model '{name}' not found.")
                return
            
            await self.config.regen_models.set(regen_models)
            await ctx.send(f"✅ Removed regeneration model '{name}'")
            
        except Exception as e:
            logger.error(f"Failed to remove regeneration model: {e}")
            await ctx.send("❌ Failed to remove regeneration model.")
    
    @regen.command(name="default")
    async def regen_set_default(self, ctx, name: str):
        """Set a model as the default regeneration model"""
        try:
            regen_models = await self.config.regen_models()
            
            # Find the model and set as default
            model_found = False
            for model in regen_models:
                if model.get("name", "").lower() == name.lower():
                    model["default"] = True
                    model_found = True
                else:
                    model["default"] = False
            
            if not model_found:
                await ctx.send(f"❌ Model '{name}' not found.")
                return
            
            await self.config.regen_models.set(regen_models)
            await ctx.send(f"✅ Set '{name}' as default regeneration model")
            
        except Exception as e:
            logger.error(f"Failed to set default model: {e}")
            await ctx.send("❌ Failed to set default model.")
    
    @regen.command(name="random")
    async def regen_random_toggle(self, ctx, enabled: bool = None):
        """Enable or disable random model selection
        
        When enabled, each AI response will use a randomly selected model from your regeneration models.
        """
        try:
            if enabled is None:
                current = await self.config.random_model_enabled()
                status = "enabled" if current else "disabled"
                await ctx.send(f"Random model selection is currently **{status}**")
                return
            
            await self.config.random_model_enabled.set(enabled)
            status = "enabled" if enabled else "disabled"
            await ctx.send(f"✅ Random model selection {status}")
            
        except Exception as e:
            logger.error(f"Failed to toggle random model: {e}")
            await ctx.send("❌ Failed to update random model setting.")
    
    @regen.command(name="stats")
    async def regen_stats(self, ctx):
        """Show regeneration and rating statistics"""
        try:
            # Get rating statistics
            stats = await self.rating_system.get_model_stats()
            
            embed = discord.Embed(
                title="Regeneration Statistics",
                color=discord.Color.green()
            )
            
            embed.add_field(
                name="Overall Ratings",
                value=f"👍 {stats['thumbs_up']}\n👎 {stats['thumbs_down']}\n📊 Total: {stats['total']}",
                inline=True
            )
            
            # Get model-specific stats
            regen_models = await self.config.regen_models()
            for model in regen_models:
                model_stats = await self.rating_system.get_model_stats(
                    model=model['name'], 
                    endpoint=model['endpoint']
                )
                if model_stats['total'] > 0:
                    embed.add_field(
                        name=f"{model['name']}",
                        value=f"👍 {model_stats['thumbs_up']}\n👎 {model_stats['thumbs_down']}\n📊 {model_stats['total']}",
                        inline=True
                    )
            
            random_enabled = await self.config.random_model_enabled()
            embed.set_footer(text=f"Random model: {'Enabled' if random_enabled else 'Disabled'}")
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Failed to get regeneration stats: {e}")
            await ctx.send("❌ Failed to retrieve statistics.")
    
    @regen.command(name="cleanup")
    @checks.is_owner()
    async def regen_cleanup(self, ctx, days: int = 30):
        """Clean up old rating data (Owner only)
        
        Parameters:
        - days: Number of days of data to keep (default: 30)
        """
        try:
            await self.rating_system.cleanup_old_ratings(days)
            await ctx.send(f"✅ Cleaned up rating data older than {days} days")
            
        except Exception as e:
            logger.error(f"Failed to cleanup ratings: {e}")
            await ctx.send("❌ Failed to cleanup rating data.")