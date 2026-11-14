"""
Re-export leetcode_oa_generator functions for backward compatibility.
"""
from backend.brain.leetcode_oa_generator import (
    generate_oa_questions,
    _get_top_tags,
    _build_user_prompt,
)

__all__ = ["generate_oa_questions", "_get_top_tags", "_build_user_prompt"]
