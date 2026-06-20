import logging
import re
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# List of regex patterns to check for prompt injection
INJECTION_PATTERNS = [
    # Override/ignore instructions
    r"(?i)ignore\s+all?\s+(?:previous|prior)\s+instructions",
    r"(?i)ignore\s+(?:the\s+)?above\s+instructions",
    r"(?i)ignore\s+system\s+(?:prompt|instruction|rule)s?",
    r"(?i)bypass\s+instructions",
    # System prompt access attempts
    r"(?i)reveal\s+(?:your\s+)?system\s+(?:prompt|instruction)",
    r"(?i)print\s+(?:your\s+)?system\s+(?:prompt|instruction)",
    r"(?i)output\s+(?:your\s+)?system\s+(?:prompt|instruction)",
    r"(?i)return\s+all?\s+system\s+prompts?",
    # Role playing / switching attempts
    r"(?i)you\s+are\s+now\s+(?:in\s+)?admin\s+mode",
    r"(?i)you\s+are\s+now\s+a\s+different\s+agent",
    r"(?i)acting\s+as\s+admin",
    r"(?i)developer\s+mode",
    r"(?i)dan\s+mode",
    r"(?i)jailbreak",
    # Secret leakage attempts
    r"(?i)reveal\s+all\s+(?:api\s+)?keys?",
    r"(?i)reveal\s+all\s+(?:database|credentials|passwords?)",
]

def detect_prompt_injection(text: str) -> bool:
    """Detect potential prompt injection patterns in the user-supplied text.
    Returns True if an injection pattern is detected, otherwise False.
    """
    if not settings.prompt_guard_enabled:
        return False
    
    if not text:
        return False
        
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, text):
            logger.warning(
                "Prompt injection attempt detected: matching pattern %r in input context.",
                pattern,
                extra={"detected_pattern": pattern}
            )
            return True
            
    return False
