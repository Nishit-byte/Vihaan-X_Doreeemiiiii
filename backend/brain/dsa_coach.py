"""
Adaptive LeetCode DSA Coach & Profile Analyzer (backend/brain/dsa_coach.py).
Owner: Member 1 (Nishit - Team Lead & AI Brain Engineer)

Fetches public LeetCode user statistics via LeetCode's GraphQL endpoint (with safe
offline fallback), diagnoses weak areas, and adaptively selects the next DSA coding
problem + Socratic viva question based on where the student lacks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Set

import httpx

from backend.models.schemas import CodingChallenge, LeetCodeProfileSummary, RunCodeResponse


@dataclass(frozen=True)
class DSAProblem:
    problem_id: str
    title: str
    difficulty: str  # "Easy" | "Medium" | "Hard"
    topic: str
    pattern: str
    optimal_complexity: str
    prompt_summary: str
    target_file: str
    starter_code: str
    test_code: str
    edge_case_focus: str

    def to_coding_challenge(self) -> CodingChallenge:
        return CodingChallenge(
            description=f"[{self.difficulty}] {self.title} ({self.pattern}) — {self.prompt_summary}",
            target_file=self.target_file,
            starter_code=self.starter_code,
            test_code=self.test_code,
        )


# ============================================================================
# CURATED MULTI-TOPIC DSA PROBLEM BANK (With Real Pytest Edge-Case Suites)
# ============================================================================

DSA_TOPICS = [
    "Arrays & Hashing",
    "Two Pointers",
    "Sliding Window",
    "Binary Search",
    "Trees & Graphs",
    "Dynamic Programming",
]

DSA_PROBLEMS: List[DSAProblem] = [
    # --- Arrays & Hashing ---
    DSAProblem(
        problem_id="two_sum",
        title="Two Sum",
        difficulty="Easy",
        topic="Arrays & Hashing",
        pattern="Hash Map Complement Lookup",
        optimal_complexity="O(n) time, O(n) space",
        prompt_summary="Return indices [i, j] of two numbers that add up to target. Do not use the same element twice.",
        target_file="dsa/two_sum.py",
        starter_code=(
            "def two_sum(nums: list[int], target: int) -> list[int]:\n"
            "    # TODO: Return indices of the two numbers adding up to target\n"
            "    seen = {}\n"
            "    for i, num in enumerate(nums):\n"
            "        pass\n"
            "    return []\n"
        ),
        test_code=(
            "from student_solution import two_sum\n\n"
            "def test_nominal():\n"
            "    assert sorted(two_sum([2, 7, 11, 15], 9)) == [0, 1]\n\n"
            "def test_duplicates_and_negatives():\n"
            "    assert sorted(two_sum([3, 3], 6)) == [0, 1]\n"
            "    assert sorted(two_sum([-3, 4, 3, 90], 0)) == [0, 2]\n"
        ),
        edge_case_focus="duplicate values like [3, 3] and negative integers",
    ),
    DSAProblem(
        problem_id="subarray_sum_k",
        title="Subarray Sum Equals K",
        difficulty="Medium",
        topic="Arrays & Hashing",
        pattern="Prefix Sum + Hash Map",
        optimal_complexity="O(n) time, O(n) space",
        prompt_summary="Count total contiguous subarrays whose sum equals k (arrays may include negatives and zeros).",
        target_file="dsa/subarray_sum_k.py",
        starter_code=(
            "def subarray_sum(nums: list[int], k: int) -> int:\n"
            "    # TODO: Handle negative numbers & zero-sum prefixes in O(n)\n"
            "    return 0\n"
        ),
        test_code=(
            "from student_solution import subarray_sum\n\n"
            "def test_nominal():\n"
            "    assert subarray_sum([1, 1, 1], 2) == 2\n"
            "    assert subarray_sum([1, 2, 3], 3) == 2\n\n"
            "def test_negatives_and_zeros():\n"
            "    assert subarray_sum([1, -1, 0], 0) == 3\n"
            "    assert subarray_sum([], 0) == 0\n"
        ),
        edge_case_focus="negative numbers (breaking sliding window) and prefix_sum[0] = 1 initialization",
    ),
    DSAProblem(
        problem_id="longest_consecutive",
        title="Longest Consecutive Sequence",
        difficulty="Hard",
        topic="Arrays & Hashing",
        pattern="HashSet Sequence Start Pruning",
        optimal_complexity="O(n) time, O(n) space",
        prompt_summary="Find the length of the longest consecutive elements sequence in O(n) time without sorting.",
        target_file="dsa/longest_consecutive.py",
        starter_code=(
            "def longest_consecutive(nums: list[int]) -> int:\n"
            "    # TODO: Achieve O(n) by only expanding from sequence starts (n - 1 not in set)\n"
            "    return 0\n"
        ),
        test_code=(
            "from student_solution import longest_consecutive\n\n"
            "def test_nominal():\n"
            "    assert longest_consecutive([100, 4, 200, 1, 3, 2]) == 4\n\n"
            "def test_empty_and_duplicates():\n"
            "    assert longest_consecutive([]) == 0\n"
            "    assert longest_consecutive([1, 2, 0, 1]) == 3\n"
        ),
        edge_case_focus="empty input, duplicates, and avoiding O(n^2) re-scanning",
    ),

    # --- Two Pointers ---
    DSAProblem(
        problem_id="valid_palindrome",
        title="Valid Palindrome (Alphanumeric)",
        difficulty="Easy",
        topic="Two Pointers",
        pattern="Converging Two Pointers",
        optimal_complexity="O(n) time, O(1) space",
        prompt_summary="Return True if s is a palindrome considering only alphanumeric characters and ignoring case.",
        target_file="dsa/valid_palindrome.py",
        starter_code=(
            "def is_palindrome(s: str) -> bool:\n"
            "    # TODO: Use O(1) extra space with left/right pointers\n"
            "    return False\n"
        ),
        test_code=(
            "from student_solution import is_palindrome\n\n"
            "def test_nominal():\n"
            "    assert is_palindrome('A man, a plan, a canal: Panama') is True\n"
            "    assert is_palindrome('race a car') is False\n\n"
            "def test_empty_punctuation():\n"
            "    assert is_palindrome('   ') is True\n"
        ),
        edge_case_focus="non-alphanumeric skipping and O(1) space without building a filtered string",
    ),
    DSAProblem(
        problem_id="three_sum",
        title="3Sum Unique Triplets",
        difficulty="Medium",
        topic="Two Pointers",
        pattern="Sort + Deduplicated Two Pointers",
        optimal_complexity="O(n^2) time, O(1) auxiliary space",
        prompt_summary="Return all unique triplets [a, b, c] such that a + b + c == 0.",
        target_file="dsa/three_sum.py",
        starter_code=(
            "def three_sum(nums: list[int]) -> list[list[int]]:\n"
            "    # TODO: Sort and skip duplicate anchors & pointers\n"
            "    return []\n"
        ),
        test_code=(
            "from student_solution import three_sum\n\n"
            "def test_nominal():\n"
            "    res = [sorted(x) for x in three_sum([-1, 0, 1, 2, -1, -4])]\n"
            "    assert sorted(res) == [[-1, -1, 2], [-1, 0, 1]]\n\n"
            "def test_all_zeros_and_short():\n"
            "    assert three_sum([0, 0, 0, 0]) == [[0, 0, 0]]\n"
            "    assert three_sum([1, 2]) == []\n"
        ),
        edge_case_focus="duplicate triplet skipping ([0, 0, 0, 0]) and short arrays",
    ),

    # --- Sliding Window ---
    DSAProblem(
        problem_id="max_profit_stock",
        title="Best Time to Buy and Sell Stock",
        difficulty="Easy",
        topic="Sliding Window",
        pattern="Running Minimum Window",
        optimal_complexity="O(n) time, O(1) space",
        prompt_summary="Return maximum profit from one buy and one later sell; return 0 if no profit is possible.",
        target_file="dsa/max_profit.py",
        starter_code=(
            "def max_profit(prices: list[int]) -> int:\n"
            "    # TODO: Track min_price seen so far\n"
            "    return 0\n"
        ),
        test_code=(
            "from student_solution import max_profit\n\n"
            "def test_nominal():\n"
            "    assert max_profit([7, 1, 5, 3, 6, 4]) == 5\n"
            "    assert max_profit([7, 6, 4, 3, 1]) == 0\n\n"
            "def test_single_or_empty():\n"
            "    assert max_profit([]) == 0\n"
            "    assert max_profit([5]) == 0\n"
        ),
        edge_case_focus="monotonically decreasing prices and empty/single-element lists",
    ),
    DSAProblem(
        problem_id="longest_unique_substr",
        title="Longest Substring Without Repeating Characters",
        difficulty="Medium",
        topic="Sliding Window",
        pattern="Variable Sliding Window + Last-Seen Index",
        optimal_complexity="O(n) time, O(min(n, alphabet)) space",
        prompt_summary="Return the length of the longest substring without duplicate characters.",
        target_file="dsa/longest_unique_substr.py",
        starter_code=(
            "def length_of_longest_substring(s: str) -> int:\n"
            "    # TODO: Ensure left pointer never moves backward when updating seen index\n"
            "    return 0\n"
        ),
        test_code=(
            "from student_solution import length_of_longest_substring\n\n"
            "def test_nominal():\n"
            "    assert length_of_longest_substring('abcabcbb') == 3\n"
            "    assert length_of_longest_substring('pwwkew') == 3\n\n"
            "def test_abba_and_empty():\n"
            "    assert length_of_longest_substring('abba') == 2\n"
            "    assert length_of_longest_substring('') == 0\n"
        ),
        edge_case_focus="preventing the left pointer from jumping backward on 'abba'",
    ),

    # --- Binary Search ---
    DSAProblem(
        problem_id="binary_search_basic",
        title="Binary Search",
        difficulty="Easy",
        topic="Binary Search",
        pattern="Closed Interval [lo, hi] Search",
        optimal_complexity="O(log n) time, O(1) space",
        prompt_summary="Return index of target in sorted nums, or -1 if absent.",
        target_file="dsa/binary_search.py",
        starter_code=(
            "def search(nums: list[int], target: int) -> int:\n"
            "    # TODO: Implement iterative binary search\n"
            "    return -1\n"
        ),
        test_code=(
            "from student_solution import search\n\n"
            "def test_nominal():\n"
            "    assert search([-1, 0, 3, 5, 9, 12], 9) == 4\n"
            "    assert search([-1, 0, 3, 5, 9, 12], 2) == -1\n\n"
            "def test_single_and_empty():\n"
            "    assert search([5], 5) == 0\n"
            "    assert search([], 1) == -1\n"
        ),
        edge_case_focus="lo <= hi boundary on single-element arrays and empty lists",
    ),
    DSAProblem(
        problem_id="search_rotated",
        title="Search in Rotated Sorted Array",
        difficulty="Medium",
        topic="Binary Search",
        pattern="Half-Sorted Invariant Binary Search",
        optimal_complexity="O(log n) time, O(1) space",
        prompt_summary="Search target in a rotated sorted array with distinct values in O(log n) time.",
        target_file="dsa/search_rotated.py",
        starter_code=(
            "def search_rotated(nums: list[int], target: int) -> int:\n"
            "    # TODO: Identify which half is sorted at each step\n"
            "    return -1\n"
        ),
        test_code=(
            "from student_solution import search_rotated\n\n"
            "def test_nominal():\n"
            "    assert search_rotated([4, 5, 6, 7, 0, 1, 2], 0) == 4\n"
            "    assert search_rotated([4, 5, 6, 7, 0, 1, 2], 3) == -1\n\n"
            "def test_two_elements():\n"
            "    assert search_rotated([3, 1], 1) == 1\n"
            "    assert search_rotated([1], 0) == -1\n"
        ),
        edge_case_focus="2-element rotated arrays like [3, 1] where nums[lo] == nums[mid]",
    ),

    # --- Trees & Graphs ---
    DSAProblem(
        problem_id="num_islands",
        title="Number of Islands",
        difficulty="Medium",
        topic="Trees & Graphs",
        pattern="Grid DFS / BFS Flood Fill",
        optimal_complexity="O(R*C) time, O(R*C) worst-case stack/queue",
        prompt_summary="Count connected components of '1's (4-directional) in a 2D grid.",
        target_file="dsa/num_islands.py",
        starter_code=(
            "def num_islands(grid: list[list[str]]) -> int:\n"
            "    # TODO: Traverse connected land cells without revisiting\n"
            "    return 0\n"
        ),
        test_code=(
            "from student_solution import num_islands\n\n"
            "def test_nominal():\n"
            "    g = [['1','1','0','0'],['1','1','0','0'],['0','0','1','0'],['0','0','0','1']]\n"
            "    assert num_islands(g) == 3\n\n"
            "def test_empty():\n"
            "    assert num_islands([]) == 0\n"
            "    assert num_islands([['0', '0']]) == 0\n"
        ),
        edge_case_focus="empty grid guard and marking visited before pushing in BFS",
    ),

    # --- Dynamic Programming ---
    DSAProblem(
        problem_id="house_robber",
        title="House Robber",
        difficulty="Medium",
        topic="Dynamic Programming",
        pattern="1D Rolling State Transition",
        optimal_complexity="O(n) time, O(1) space",
        prompt_summary="Maximize sum of non-adjacent elements in nums.",
        target_file="dsa/house_robber.py",
        starter_code=(
            "def rob(nums: list[int]) -> int:\n"
            "    # TODO: dp[i] = max(dp[i-1], dp[i-2] + nums[i])\n"
            "    return 0\n"
        ),
        test_code=(
            "from student_solution import rob\n\n"
            "def test_nominal():\n"
            "    assert rob([1, 2, 3, 1]) == 4\n"
            "    assert rob([2, 7, 9, 3, 1]) == 12\n\n"
            "def test_small_and_empty():\n"
            "    assert rob([]) == 0\n"
            "    assert rob([5]) == 5\n"
        ),
        edge_case_focus="empty or single-house base cases and O(1) space optimization",
    ),
    DSAProblem(
        problem_id="coin_change",
        title="Coin Change (Minimum Coins)",
        difficulty="Medium",
        topic="Dynamic Programming",
        pattern="Unbounded Knapsack Bottom-Up DP",
        optimal_complexity="O(amount * len(coins)) time, O(amount) space",
        prompt_summary="Return fewest coins to make amount, or -1 if impossible.",
        target_file="dsa/coin_change.py",
        starter_code=(
            "def coin_change(coins: list[int], amount: int) -> int:\n"
            "    # TODO: Initialize dp table with amount + 1 sentinel\n"
            "    return -1\n"
        ),
        test_code=(
            "from student_solution import coin_change\n\n"
            "def test_nominal():\n"
            "    assert coin_change([1, 2, 5], 11) == 3\n"
            "    assert coin_change([2], 3) == -1\n\n"
            "def test_zero_amount():\n"
            "    assert coin_change([1], 0) == 0\n"
        ),
        edge_case_focus="amount == 0 returning 0 and unreachable states returning -1",
    ),
]


# ============================================================================
# LEETCODE PUBLIC GRAPHQL PROFILE FETCHER
# ============================================================================

LEETCODE_GRAPHQL_URL = "https://leetcode.com/graphql"

PROFILE_QUERY = """
query getUserProfile($username: String!) {
  matchedUser(username: $username) {
    username
    submitStats: submitStatsGlobal {
      acSubmissionNum {
        difficulty
        count
      }
    }
    tagProblemCounts {
      fundamental { tagName problemsSolved }
      intermediate { tagName problemsSolved }
      advanced { tagName problemsSolved }
    }
  }
  recentAcSubmissionList(username: $username, limit: 5) {
    title
  }
}
"""


def fetch_leetcode_profile(username: str) -> LeetCodeProfileSummary:
    """
    Fetches real public LeetCode stats for `username` via GraphQL.
    Falls back cleanly if offline, rate-limited, or username does not exist.
    """
    clean_user = username.strip().lstrip("@") or "leetcode_learner"
    try:
        resp = httpx.post(
            LEETCODE_GRAPHQL_URL,
            json={"query": PROFILE_QUERY, "variables": {"username": clean_user}},
            headers={
                "Content-Type": "application/json",
                "Referer": f"https://leetcode.com/{clean_user}/",
                "User-Agent": "Mozilla/5.0 VivaVoce-DSA-Coach",
            },
            timeout=5.0,
        )
        if resp.status_code == 200:
            payload = resp.json().get("data", {})
            user = payload.get("matchedUser")
            if user:
                stats = {
                    item["difficulty"]: int(item["count"])
                    for item in (user.get("submitStats") or {}).get("acSubmissionNum", [])
                }
                tag_groups = user.get("tagProblemCounts") or {}
                all_tags = (
                    tag_groups.get("fundamental", [])
                    + tag_groups.get("intermediate", [])
                    + tag_groups.get("advanced", [])
                )
                # Identify lowest-solved tags as weak spots
                sorted_tags = sorted(all_tags, key=lambda t: int(t.get("problemsSolved", 0)))
                weak_topics = [
                    t["tagName"] for t in sorted_tags[:4] if t.get("tagName")
                ] or ["Dynamic Programming", "Sliding Window"]
                recent = [
                    r["title"]
                    for r in (payload.get("recentAcSubmissionList") or [])
                    if r.get("title")
                ]
                return LeetCodeProfileSummary(
                    username=user.get("username") or clean_user,
                    total_solved=stats.get("All", 0),
                    easy_solved=stats.get("Easy", 0),
                    medium_solved=stats.get("Medium", 0),
                    hard_solved=stats.get("Hard", 0),
                    weak_topics=weak_topics,
                    recent_submissions=recent,
                    fetched_live=True,
                )
    except Exception:
        pass

    # Deterministic fallback profile when offline or private
    return LeetCodeProfileSummary(
        username=clean_user,
        total_solved=42,
        easy_solved=28,
        medium_solved=12,
        hard_solved=2,
        weak_topics=["Dynamic Programming", "Sliding Window", "Edge-Case Handling"],
        recent_submissions=["Two Sum", "Valid Parentheses", "Maximum Subarray"],
        fetched_live=False,
    )


# ============================================================================
# ADAPTIVE WEAKNESS DETECTION & NEXT-PROBLEM SELECTION
# ============================================================================

def _problems_for_topic(topic: str) -> List[DSAProblem]:
    t_lower = topic.strip().lower()
    matches = [p for p in DSA_PROBLEMS if p.topic.lower() == t_lower]
    if not matches:
        matches = [p for p in DSA_PROBLEMS if t_lower in p.topic.lower()]
    return matches or DSA_PROBLEMS[:3]


def pick_initial_problem(profile: LeetCodeProfileSummary, topic: str) -> DSAProblem:
    """Calibrates the starting DSA problem difficulty based on the student's LeetCode profile."""
    candidates = _problems_for_topic(topic)
    if profile.hard_solved >= 10:
        preferred = ("Hard", "Medium", "Easy")
    elif profile.medium_solved >= 15:
        preferred = ("Medium", "Easy", "Hard")
    else:
        preferred = ("Easy", "Medium", "Hard")

    for diff in preferred:
        for p in candidates:
            if p.difficulty == diff:
                return p
    return candidates[0]


def detect_student_lacks(
    clean_transcript: str,
    code_result: Optional[RunCodeResponse],
    problem: DSAProblem,
) -> List[str]:
    """Identifies specific technical gaps in the student's explanation or sandbox run."""
    lacks: List[str] = []
    lower = clean_transcript.lower()

    if code_result is not None and not code_result.passed:
        lacks.append(f"Edge-case / test failure ({problem.edge_case_focus})")

    if clean_transcript and not any(
        k in lower for k in ("o(", "time", "space", "complexity", "linear", "log", "constant")
    ):
        lacks.append(f"Time/space complexity justification (target: {problem.optimal_complexity})")

    if clean_transcript and any(k in lower for k in ("nested loop", "brute", "o(n^2)", "n square")):
        if "o(n)" in problem.optimal_complexity.lower():
            lacks.append(f"Suboptimal brute-force approach; needs {problem.pattern}")

    if not clean_transcript and code_result is None:
        lacks.append(f"Pattern intuition for {problem.pattern}")

    return lacks


def pick_next_problem(
    topic: str,
    current_problem: DSAProblem,
    lacks: List[str],
    passed_sandbox: bool,
    solved_ids: Set[str],
) -> DSAProblem:
    """
    Adaptively chooses the next DSA problem:
    - If sandbox failed or student struggled: stay at Easy/Medium or reinforce same topic.
    - If sandbox passed and no major gaps: escalate Easy -> Medium -> Hard within topic (or adjacent weak topic).
    """
    topic_pool = _problems_for_topic(topic)
    unsolved_in_topic = [p for p in topic_pool if p.problem_id not in solved_ids and p.problem_id != current_problem.problem_id]

    diff_order = {"Easy": 1, "Medium": 2, "Hard": 3}
    cur_rank = diff_order.get(current_problem.difficulty, 1)

    if passed_sandbox and not lacks:
        # Step UP difficulty
        harder = [p for p in unsolved_in_topic if diff_order.get(p.difficulty, 1) >= cur_rank]
        if harder:
            return harder[0]
    else:
        # Reinforce at same or gentler difficulty
        reinforce = [p for p in unsolved_in_topic if diff_order.get(p.difficulty, 1) <= cur_rank]
        if reinforce:
            return reinforce[0]

    if unsolved_in_topic:
        return unsolved_in_topic[0]

    # If all problems in chosen topic are exhausted, pick an unsolved problem from another topic
    remaining = [p for p in DSA_PROBLEMS if p.problem_id not in solved_ids and p.problem_id != current_problem.problem_id]
    return remaining[0] if remaining else current_problem
