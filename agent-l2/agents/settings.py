"""Layer 2 settings: Groq model names and runtime limits (all env-overridable)."""
import os

from dotenv import load_dotenv

load_dotenv()

#: Strong reasoning model: planner, quant cross-check, verifier, synthesis.
MODEL_LARGE: str = os.getenv("GROQ_MODEL_LARGE", "llama-3.3-70b-versatile")
#: Fast, cheap model: high-volume extraction (market data, filings, news).
MODEL_FAST: str = os.getenv("GROQ_MODEL_FAST", "llama-3.1-8b-instant")

#: Max concurrent Groq calls from the parallel executor (protects rate limits).
MAX_CONCURRENCY: int = int(os.getenv("GROQ_MAX_CONCURRENCY", "4"))
#: Raw tool data is truncated to this many characters before prompting.
MAX_RAW_CHARS: int = int(os.getenv("MAX_RAW_CHARS", "20000"))

CONFIDENCE_THRESHOLD: float = 0.6
CONFLICT_THRESHOLD_PCT: float = 5.0
