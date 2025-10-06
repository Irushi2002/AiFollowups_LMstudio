import logging
import re
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import hashlib

# NLTK imports for stemming and sentiment
import nltk
from nltk.stem import PorterStemmer
from nltk.tokenize import word_tokenize
from nltk.sentiment import SentimentIntensityAnalyzer

# TextBlob as alternative for sentiment
try:
    from textblob import TextBlob
    TEXTBLOB_AVAILABLE = True
except ImportError:
    TEXTBLOB_AVAILABLE = False

from config import Config
from database import get_database

logger = logging.getLogger(__name__)

# Download required NLTK data
try:
    nltk.download('punkt', quiet=True)
    nltk.download('punkt_tab', quiet=True) 
    nltk.download('vader_lexicon', quiet=True)
    NLTK_AVAILABLE = True
except Exception as e:
    logger.warning(f"NLTK download failed: {e}")
    NLTK_AVAILABLE = False

class QualityScorer:
    """
    Heuristic quality scoring system for work updates
    Combines multiple checks into a 0-10 quality score
    """
    
    def __init__(self):
        self.config = Config()
        self.db = get_database()
        
        # Initialize NLTK components
        if NLTK_AVAILABLE:
            self.stemmer = PorterStemmer()
            self.sentiment_analyzer = SentimentIntensityAnalyzer()
            
            # Create keyword stems for faster comparison
            self.keyword_stems = {
                self.stemmer.stem(keyword.lower()) 
                for keyword in self.config.QUALITY_KEYWORDS
            }
        else:
            self.stemmer = None
            self.sentiment_analyzer = None
            self.keyword_stems = set()
            
        logger.info(f"Quality scorer initialized with {len(self.config.QUALITY_KEYWORDS)} keywords")
        if NLTK_AVAILABLE:
            logger.info(f"NLTK enabled - stemmed to {len(self.keyword_stems)} keyword stems")
        else:
            logger.warning("NLTK not available - using basic keyword matching")
    
    async def calculate_quality_score(
        self, 
        work_description: str, 
        intern_id: str, 
        update_date: str = None
    ) -> Dict:
        """
        Calculate comprehensive quality score for a work update
        
        Returns:
            Dict containing score, individual component scores, and flags
        """
        try:
            # Ensure we have text to analyze
            if not work_description or not work_description.strip():
                return self._create_score_result(0, {
                    "error": "Empty work description",
                    "word_count": 0,
                    "keyword_found": False,
                    "sentiment_score": 0,
                    "is_repetition": False,
                    "has_structure": False,
                    "flagged": True,
                    "flag_reasons": ["empty_description"]
                })
            
            content = work_description.strip()
            
            # 1. Word Count Score (0-4 points)
            word_count_score, word_count = self._calculate_word_count_score(content)
            
            # 2. Keyword Presence Score (0-2 points)
            keyword_score, keyword_found = self._calculate_keyword_score(content)
            
            # 3. Sentiment Score (0-2 points)
            sentiment_score, sentiment_polarity, sentiment_label = self._calculate_sentiment_score(content)
            
            # 4. Repetition Check (-2 penalty if repeated)
            repetition_penalty, is_repetition = await self._check_repetition(content, intern_id, update_date)
            
            # 5. Structure Check (0-1 points)
            structure_score, has_structure = self._check_structure(content)
            
            # 6. Time-based behavior (future enhancement - placeholder for now)
            time_penalty = 0   
            
            # Calculate raw score
            raw_score = (
                word_count_score +
                keyword_score +
                sentiment_score +
                structure_score +
                repetition_penalty +
                time_penalty
            )
            
            # Clip to [0,9] then scale to [0,10]
            clipped_score = max(0, min(9, raw_score))
            final_score = round((clipped_score * 10) / 9, 1)
            
            # Determine if flagged based on multiple criteria
            flag_reasons = []
            flagged = False
            
            # Flagging rules
            if final_score < self.config.QUALITY_SCORE_THRESHOLD:
                flag_reasons.append("low_quality_score")
                flagged = True
                
            if is_repetition:
                flag_reasons.append("repetitive_content")
                flagged = True
                
            if word_count < self.config.WORD_COUNT_WEAK_THRESHOLD:
                flag_reasons.append("too_short")
                flagged = True
                
            if sentiment_label == "very_negative":
                flag_reasons.append("very_negative_sentiment")
                flagged = True
            
            # Build detailed result
            result = self._create_score_result(final_score, {
                "word_count": word_count,
                "word_count_score": word_count_score,
                "keyword_found": keyword_found,
                "keyword_score": keyword_score,
                "sentiment_polarity": sentiment_polarity,
                "sentiment_label": sentiment_label,
                "sentiment_score": sentiment_score,
                "is_repetition": is_repetition,
                "repetition_penalty": repetition_penalty,
                "has_structure": has_structure,
                "structure_score": structure_score,
                "time_penalty": time_penalty,
                "raw_score": raw_score,
                "flagged": flagged,
                "flag_reasons": flag_reasons,
                "needs_followup": flagged  # Flagged content needs follow-up
            })
            
            logger.info(f"Quality score calculated: {final_score}/10 (flagged: {flagged})")
            return result
            
        except Exception as e:
            logger.error(f"Error calculating quality score: {e}")
            return self._create_score_result(0, {
                "error": str(e),
                "flagged": True,
                "flag_reasons": ["scoring_error"],
                "needs_followup": True
            })
    
    def _calculate_word_count_score(self, content: str) -> Tuple[int, int]:
        """
        Calculate word count score (0-4 points)
        """
        word_count = len(content.split())
        
        if word_count >= self.config.WORD_COUNT_OK_THRESHOLD:   
            return 4, word_count
        elif word_count >= self.config.WORD_COUNT_WEAK_THRESHOLD:   
            return 2, word_count
        else:  
            return 0, word_count
    
    def _calculate_keyword_score(self, content: str) -> Tuple[int, bool]:
        """
        Calculate keyword presence score using stemming (0-2 points)
        """
        if not NLTK_AVAILABLE or not self.keyword_stems:
            # Fallback to basic keyword matching
            content_lower = content.lower()
            for keyword in self.config.QUALITY_KEYWORDS:
                if keyword.lower() in content_lower:
                    return 2, True
            return 0, False
        
        try:
            # Tokenize and stem the content
            tokens = word_tokenize(content.lower())
            content_stems = {self.stemmer.stem(token) for token in tokens if token.isalnum()}
            
            # Check for intersection with keyword stems
            if content_stems & self.keyword_stems:
                return 2, True
            else:
                return 0, False
                
        except Exception as e:
            logger.warning(f"Keyword scoring failed, using fallback: {e}")
          
            content_lower = content.lower()
            for keyword in self.config.QUALITY_KEYWORDS:
                if keyword.lower() in content_lower:
                    return 2, True
            return 0, False
    
    def _calculate_sentiment_score(self, content: str) -> Tuple[int, float, str]:
        """
        Calculate sentiment score (0-2 points)
        Returns: (score, polarity, label)
        """
        polarity = 0.0
        label = "neutral"
        
        if NLTK_AVAILABLE and self.sentiment_analyzer:
            try:
                # Use VADER sentiment analyzer
                scores = self.sentiment_analyzer.polarity_scores(content)
                polarity = scores['compound']  
            except Exception as e:
                logger.warning(f"VADER sentiment analysis failed: {e}")
        
        elif TEXTBLOB_AVAILABLE:
            try:
                # Use TextBlob as fallback
                blob = TextBlob(content)
                polarity = blob.sentiment.polarity  # Range -1 to 1
            except Exception as e:
                logger.warning(f"TextBlob sentiment analysis failed: {e}")
        
        # Determine sentiment label and score
        if polarity < self.config.NEGATIVE_SENTIMENT_THRESHOLD:  # < -0.3
            label = "very_negative"
            score = 0
        elif polarity < self.config.POSITIVE_SENTIMENT_THRESHOLD:  # -0.3 to 0.2
            label = "neutral"
            score = 1
        else:  # > 0.2
            label = "positive"
            score = 2
        
        return score, polarity, label
    
    async def _check_repetition(self, content: str, intern_id: str, update_date: str = None) -> Tuple[int, bool]:
        """
        Check for repetitive content (-2 penalty if repeated)
        """
        try:
            # Create hash of current content
            content_hash = hashlib.md5(content.lower().encode()).hexdigest()
            
            # Look for recent work updates with same content
            work_updates_collection = self.db[Config.WORK_UPDATES_COLLECTION]
            temp_work_updates_collection = self.db[Config.TEMP_WORK_UPDATES_COLLECTION]
            
            # Check last 5 updates from both collections
            query_filter = {"internId": intern_id} if hasattr(self, 'logbook_mode') else {"userId": intern_id}
            
            # Exclude current update if we have the date
            if update_date:
                query_filter["date"] = {"$ne": update_date}
            
            # Check permanent collection
            recent_permanent = await work_updates_collection.find(
                query_filter
            ).sort("submittedAt", -1).limit(5).to_list(5)
            
            # Check temp collection
            recent_temp = await temp_work_updates_collection.find(
                query_filter
            ).sort("submittedAt", -1).limit(5).to_list(5)
            
            # Combine and check for hash matches
            all_recent = recent_permanent + recent_temp
            
            for update in all_recent:
                # Get description field (varies by collection structure)
                description = update.get("description") or update.get("task") or ""
                if description:
                    existing_hash = hashlib.md5(description.lower().encode()).hexdigest()
                    if existing_hash == content_hash:
                        logger.info(f"Repetition detected for intern {intern_id}")
                        return -2, True
            
            return 0, False
            
        except Exception as e:
            logger.warning(f"Repetition check failed: {e}")
            return 0, False
    
    def _check_structure(self, content: str) -> Tuple[int, bool]:
        """
        Check for structured content (0-1 points)
        Looks for sections like "What I did", "Next", "Blockers", etc.
        """
        structure_keywords = [
            "what i did", "what i worked on", "completed", "tasks",
            "next", "tomorrow", "plans", "planning",
            "blockers", "challenges", "issues", "problems",
            "progress", "status", "update"
        ]
        
        content_lower = content.lower()
        
        # Check for presence of structure keywords
        found_structure_words = 0
        for keyword in structure_keywords:
            if keyword in content_lower:
                found_structure_words += 1
        
        # Also check for bullet points, numbers, or section separators
        has_bullets = bool(re.search(r'[•\-\*\d+\.]', content))
        has_line_breaks = content.count('\n') >= 2
        
        # Score based on structure indicators
        if found_structure_words >= 2 or has_bullets or has_line_breaks:
            return 1, True
        else:
            return 0, False
    
    def _create_score_result(self, score: float, details: Dict) -> Dict:
        """Create standardized score result"""
        return {
            "quality_score": score,
            "timestamp": datetime.now().isoformat(),
            **details
        }

    async def should_trigger_followup(self, work_description: str, intern_id: str, update_date: str = None) -> Tuple[bool, Dict]:
        """
        Main method to determine if follow-up is needed based on quality score
        
        Returns:
            Tuple of (needs_followup: bool, score_details: Dict)
        """
        score_result = await self.calculate_quality_score(work_description, intern_id, update_date)
        
        needs_followup = score_result.get("needs_followup", False)
        quality_score = score_result.get("quality_score", 0)
        
        logger.info(f"Follow-up decision for intern {intern_id}: "
                   f"Score={quality_score}, Needs followup={needs_followup}")
        
        return needs_followup, score_result

# Global quality scorer instance
quality_scorer: Optional[QualityScorer] = None

def initialize_quality_scorer():
    """Initialize the global quality scorer"""
    global quality_scorer
    
    quality_scorer = QualityScorer()
    logger.info("Global quality scorer initialized")

def get_quality_scorer() -> QualityScorer:
    """Get the global quality scorer instance"""
    if quality_scorer is None:
        raise RuntimeError("Quality scorer not initialized. Call initialize_quality_scorer() first")
    
    return quality_scorer