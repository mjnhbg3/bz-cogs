import logging
import json
from datetime import datetime
from typing import Dict, List, Optional
from redbot.core import Config

logger = logging.getLogger("red.bz_cogs.aiuser")

class ResponseRating:
    """Handles response rating and logging"""
    
    def __init__(self, config: Config):
        self.config = config
    
    async def log_rating(self, message_id: int, user_id: int, guild_id: int, 
                        model: str, endpoint: str, rating: str, 
                        response_content: str = None):
        """Log a user rating for a response"""
        try:
            ratings = await self.config.response_ratings()
            if not isinstance(ratings, dict):
                ratings = {}
            
            rating_data = {
                "user_id": user_id,
                "guild_id": guild_id,
                "model": model,
                "endpoint": endpoint,
                "rating": rating,  # "thumbs_up" or "thumbs_down"
                "timestamp": datetime.now().isoformat(),
                "response_content": response_content[:500] if response_content else None  # Truncate for storage
            }
            
            ratings[str(message_id)] = rating_data
            await self.config.response_ratings.set(ratings)
            
            logger.info(f"Logged {rating} rating for message {message_id} from user {user_id}")
            
        except Exception as e:
            logger.error(f"Failed to log rating: {e}")
    
    async def get_rating(self, message_id: int) -> Optional[Dict]:
        """Get rating for a specific message"""
        try:
            ratings = await self.config.response_ratings()
            return ratings.get(str(message_id))
        except Exception as e:
            logger.error(f"Failed to get rating: {e}")
            return None
    
    async def get_model_stats(self, model: str = None, endpoint: str = None) -> Dict:
        """Get aggregated statistics for ratings"""
        try:
            ratings = await self.config.response_ratings()
            if not isinstance(ratings, dict):
                return {"thumbs_up": 0, "thumbs_down": 0, "total": 0}
            
            thumbs_up = 0
            thumbs_down = 0
            
            for rating_data in ratings.values():
                if isinstance(rating_data, dict):
                    # Filter by model/endpoint if specified
                    if model and rating_data.get("model") != model:
                        continue
                    if endpoint and rating_data.get("endpoint") != endpoint:
                        continue
                    
                    if rating_data.get("rating") == "thumbs_up":
                        thumbs_up += 1
                    elif rating_data.get("rating") == "thumbs_down":
                        thumbs_down += 1
            
            return {
                "thumbs_up": thumbs_up,
                "thumbs_down": thumbs_down,
                "total": thumbs_up + thumbs_down
            }
            
        except Exception as e:
            logger.error(f"Failed to get model stats: {e}")
            return {"thumbs_up": 0, "thumbs_down": 0, "total": 0}
    
    async def cleanup_old_ratings(self, days_to_keep: int = 30):
        """Clean up ratings older than specified days"""
        try:
            ratings = await self.config.response_ratings()
            if not isinstance(ratings, dict):
                return
            
            cutoff_date = datetime.now().timestamp() - (days_to_keep * 24 * 60 * 60)
            cleaned_ratings = {}
            
            for message_id, rating_data in ratings.items():
                if isinstance(rating_data, dict) and "timestamp" in rating_data:
                    try:
                        rating_timestamp = datetime.fromisoformat(rating_data["timestamp"]).timestamp()
                        if rating_timestamp > cutoff_date:
                            cleaned_ratings[message_id] = rating_data
                    except:
                        # Keep ratings with invalid timestamps for now
                        cleaned_ratings[message_id] = rating_data
                        
            await self.config.response_ratings.set(cleaned_ratings)
            logger.info(f"Cleaned up old ratings, kept {len(cleaned_ratings)} out of {len(ratings)}")
            
        except Exception as e:
            logger.error(f"Failed to cleanup old ratings: {e}")