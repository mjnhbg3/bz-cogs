import asyncio
import logging
import re
from redbot.core import Config, commands
from aiuser.config.constants import REGEX_RUN_TIMEOUT
from aiuser.utils.utilities import to_thread

logger = logging.getLogger("red.bz_cogs.aiuser")

# Use to_thread to compile & apply a regex pattern
@to_thread(timeout=REGEX_RUN_TIMEOUT)
def compile_and_apply(pattern_str: str, text: str) -> str:
    pattern = re.compile(pattern_str)
    return pattern.sub('', text).strip(' \n')

async def remove_patterns_from_response(ctx: commands.Context, config: Config, response: str) -> str:
    # Get patterns from config and replace "{botname}".
    patterns = await config.guild(ctx.guild).removelist_regexes()
    botname = ctx.message.guild.me.nick or ctx.bot.user.display_name
    patterns = [p.replace(r'{botname}', botname) for p in patterns]

    # Expand patterns that have "{authorname}" based on recent authors.
    authors = {
        msg.author.display_name async for msg in ctx.channel.history(limit=10)
        if msg.author != ctx.guild.me
    }
    expanded_patterns = []
    for pattern in patterns:
        if '{authorname}' in pattern:
            for author in authors:
                expanded_patterns.append(pattern.replace(r'{authorname}', author))
        else:
            expanded_patterns.append(pattern)

    # Apply each pattern sequentially.
    cleaned = response.strip(' \n')
    for pattern in expanded_patterns:
        try:
            cleaned = await compile_and_apply(pattern, cleaned)
        except asyncio.TimeoutError:
            logger.warning(f"Timeout applying regex pattern: {pattern}")
        except Exception:
            logger.warning(f"Error applying regex pattern: {pattern}", exc_info=True)
    return cleaned