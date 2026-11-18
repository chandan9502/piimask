"""piimask: mask UK personal data before text goes to an LLM, then restore it."""
from .core import KINDS, MaskResult, Match, find_pii, mask, restore

__version__ = "0.1.0"
__all__ = ["KINDS", "Match", "MaskResult", "__version__", "find_pii", "mask", "restore"]
