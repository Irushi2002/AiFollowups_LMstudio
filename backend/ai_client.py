"""
LM Studio AI Client - Local AI Provider Only
Replaces cloud APIs (Gemini/Groq) with local LM Studio
"""

from openai import OpenAI
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class LMStudioClient:
    """
    Simple client for LM Studio - No API keys, No rate limits
    """
    
    def __init__(self, base_url: str = "http://localhost:1234/v1"):
        """
        Initialize LM Studio client
        
        Args:
            base_url: LM Studio server URL (default: localhost:1234)
        """
        self.base_url = base_url
        self.client = OpenAI(
            base_url=base_url,
            api_key="not-needed"  # LM Studio doesn't need API key
        )
        self.name = "LMStudio_Local"
        self.provider = "lmstudio"
        
        logger.info(f"LM Studio client initialized: {base_url}")
    
    async def generate_content(self, prompt: str) -> Optional[str]:
        """
        Generate content using LM Studio
        
        Args:
            prompt: The input prompt
            
        Returns:
            Generated text or None if failed
        """
        try:
            response = self.client.chat.completions.create(
                model="local-model",  # LM Studio uses this placeholder
                messages=[
                    {
                        "role": "system",
                        "content": "You are an AI assistant helping supervisors track intern progress. Generate clear, specific follow-up questions."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.7,
                max_tokens=500,
                timeout=120
            )
            
            if response.choices and response.choices[0].message.content:
                content = response.choices[0].message.content.strip()
                logger.info(f"LM Studio generated response: {len(content)} chars")
                return content
            else:
                logger.warning("LM Studio returned empty response")
                return None
                
        except Exception as e:
            logger.error(f"LM Studio generation failed: {e}")
            return None
    
    async def test_connection(self) -> Dict[str, Any]:
        """
        Test the connection to LM Studio
        
        Returns:
            Dict with test results
        """
        test_prompt = "Generate a simple test response: 'AI connection working'"
        
        try:
            result = await self.generate_content(test_prompt)
            
            if result and "working" in result.lower():
                return {
                    "status": "working",
                    "provider": "lmstudio",
                    "name": self.name,
                    "response": result[:100] + "..." if len(result) > 100 else result,
                    "server_url": self.base_url
                }
            else:
                return {
                    "status": "failed",
                    "provider": "lmstudio",
                    "name": self.name,
                    "error": "Invalid response or connection failed",
                    "response": result[:50] + "..." if result else None,
                    "server_url": self.base_url
                }
                
        except Exception as e:
            return {
                "status": "error",
                "provider": "lmstudio",
                "name": self.name,
                "error": str(e),
                "server_url": self.base_url,
                "hint": "Make sure LM Studio server is running on port 1234"
            }


class AIProviderManager:
    """
    Simplified manager for LM Studio only
    """
    
    def __init__(self, lmstudio_url: str = "http://localhost:1234/v1"):
        """
        Initialize manager with LM Studio client
        """
        self.client = LMStudioClient(lmstudio_url)
        logger.info("AI Provider Manager initialized with LM Studio only")
    
    def get_client(self, provider_name: str = None) -> LMStudioClient:
        """Get LM Studio client (provider_name ignored for compatibility)"""
        return self.client
    
    async def test_all_connections(self) -> Dict[str, Any]:
        """Test LM Studio connection"""
        result = await self.client.test_connection()
        return {
            "LMStudio_Local": result
        }