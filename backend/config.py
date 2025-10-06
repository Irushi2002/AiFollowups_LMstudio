import os
from dotenv import load_dotenv
from typing import List, Dict

load_dotenv()

class Config:
    # MongoDB Configuration
    MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
    DATABASE_NAME = os.getenv("DATABASE_NAME", "intern_progress")
    
    # LM Studio Configuration (replaces all API keys)
    LMSTUDIO_URL = os.getenv("LMSTUDIO_URL", "http://localhost:1234/v1")
    
    # Application Configuration
    SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-here")
    DEBUG = os.getenv("DEBUG", "False").lower() == "true"
    
    # Collections
    WORK_UPDATES_COLLECTION = "work_updates"
    TEMP_WORK_UPDATES_COLLECTION = "temp_work_updates"
    FOLLOWUP_SESSIONS_COLLECTION = "followup_sessions"
    DAILY_RECORDS_COLLECTION = "dailyrecords"
    
    # Quality Scoring Configuration
    QUALITY_SCORE_THRESHOLD = float(os.getenv("QUALITY_SCORE_THRESHOLD", "6.0"))
    
    # Quality scoring thresholds (tunable)
    WORD_COUNT_WEAK_THRESHOLD = int(os.getenv("WORD_COUNT_WEAK_THRESHOLD", "10"))
    WORD_COUNT_OK_THRESHOLD = int(os.getenv("WORD_COUNT_OK_THRESHOLD", "25"))
    
    # Keyword list for action words 
    DEFAULT_KEYWORDS = [
        "implement", "fix", "test", "deploy", "review", "design", 
        "bug", "ticket", "block", "wip", "refactor", "docs", "complete",
        "debug", "meeting", "plann", "research", "learn",
        "code", "develop", "build", "write", "updat"
    ]
    
    @property
    def QUALITY_KEYWORDS(self) -> List[str]:
        """Get quality keywords from env or use defaults"""
        env_keywords = os.getenv("QUALITY_KEYWORDS")
        if env_keywords:
            return env_keywords.split(",")
        return self.DEFAULT_KEYWORDS
    
    # Sentiment analysis thresholds
    NEGATIVE_SENTIMENT_THRESHOLD = float(os.getenv("NEGATIVE_SENTIMENT_THRESHOLD", "-0.3"))
    POSITIVE_SENTIMENT_THRESHOLD = float(os.getenv("POSITIVE_SENTIMENT_THRESHOLD", "0.2"))
    
    @classmethod
    def validate_config_simplified(cls):
        """Validate required configuration"""
        # Just check MongoDB connection - no API keys needed!
        if not cls.MONGODB_URL:
            raise ValueError("MONGODB_URL environment variable is required")
        
        logger.info("✓ Configuration validated - Using LM Studio (no API keys needed)")
        return True
    
    @classmethod
    def get_api_key_summary(cls):
        """Get summary of configuration for logging"""
        return {
            "ai_provider": "LMStudio (Local)",
            "api_keys_required": 0,
            "cost_per_request": 0.0,
            "rate_limits": "Hardware limited only",
            "server_url": cls.LMSTUDIO_URL,
            "authentication_method": "user_id_in_request_field"
        }

# Add logger for validation
import logging
logger = logging.getLogger(__name__)