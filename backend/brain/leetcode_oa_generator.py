"""
Dynamic LeetCode Adaptive OA Generator (backend/brain/leetcode_oa_generator.py).
Owner: Senior Full-Stack Engineer (VivaVoce)

Generates customized, dynamic 5-question Online Assessments (OA) strictly
tailored to a candidate's LeetCode profile and skill telemetry using Gemini 2.5/3.5 Flash:
- Category 1 (PUBLIC_SOLVED_LIST): Mutates and twists exact recently solved question concepts.
- Category 2 (HIDDEN_TOPIC_COUNTS_ONLY): Synthesizes questions strictly weighted by top tier counts:
    * 1 Easy: Top Fundamental + Intermediate tags
    * 2 Medium: Combining top Intermediate + Advanced tags
    * 2 Hard: Stress-testing candidate's claimed strongest Advanced tags (e.g. DP, Union-Find, Backtracking)
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv

from backend.models.schemas import (
    LeetCodeProfileData,
    OAExample,
    OAQuestion,
    OATestCase,
    SkillTagStat,
)

load_dotenv()
logger = logging.getLogger("vivavoce.leetcode_oa_generator")

OA_SYSTEM_PROMPT = """You are the VivaVoce Adaptive Online Assessment (OA) Engine for LeetCode candidate interviews.
Your task is to generate a rigorous, production-grade 5-question coding assessment tailored specifically and uniquely to the candidate's LeetCode profile.

You must handle two categories of profiles:
1. Category 1 (`PUBLIC_SOLVED_LIST`): The candidate has public solved questions. Mutate or twist the concepts of these exact solved problems (e.g., adding state constraints, range queries, or reverse lookup).
2. Category 2 (`HIDDEN_TOPIC_COUNTS_ONLY`): Solved list is hidden. Weight questions strictly by their claimed topic counts:
   - 1 Easy question (OA-1): Grounded in their top Fundamental + Intermediate tags.
   - 2 Medium questions (OA-2, OA-3): Combining their top Intermediate + Advanced tags.
   - 2 Hard questions (OA-4, OA-5): Stress-testing their claimed strongest Advanced tags (e.g., Dynamic Programming, Union-Find, Backtracking, Graphs).

### STRICT REQUIREMENTS PER QUESTION:
1. `question_id`: Exactly "OA-1", "OA-2", "OA-3", "OA-4", "OA-5".
2. `title`: Clear, descriptive title.
3. `difficulty`: "Easy" for OA-1, "Medium" for OA-2 and OA-3, "Hard" for OA-4 and OA-5.
4. `topics`: List of 1-3 algorithmic topics.
5. `selection_reason`: Explicitly cite WHY this question was generated from Category 1 solved titles OR Category 2 topic counts (mentioning specific tag names and solved counts).
6. `problem_statement`: Detailed specification with explicit "Input Format" (stdin) and "Output Format" (stdout).
7. `examples`: 2 concrete examples with input, output, and explanation.
8. `constraints`: 2-4 standard constraints (e.g., 1 <= n <= 10^5, Time limit: 2.0s).
9. `test_cases`: Exactly 5 to 6 test cases using standard stdin and stdout:
   - 2 visible cases with `"is_hidden": false` matching the examples.
   - 3 to 4 boundary/edge/stress cases with `"is_hidden": true`.
   `stdin` must be the exact raw string fed to standard input (including newlines if multi-line).
   `expected_output` must be the exact expected string printed to standard output.
10. `starter_templates`: Object with keys "cpp", "python", "java", "javascript" containing authentic LeetCode `class Solution` method signatures (NO `int main()`, NO standard headers, clean empty method bodies with type annotations).
11. `driver_code`: Object with keys "cpp", "python", "java", "javascript" containing the hidden driver that parses stdin, invokes `Solution`, and prints the return value to stdout. In `driver_code['cpp']`, you MUST use valid syntax: `#include <iostream>` or start directly with `int main() { ... }`. NEVER write `#iostream` or other invalid preprocessor directives.

OUTPUT STRICT JSON ONLY with the key "oa_questions":
{
  "oa_questions": [
    {
      "question_id": "OA-1",
      "title": "...",
      "difficulty": "Easy",
      "topics": ["Array", "Hash Table"],
      "selection_reason": "...",
      "problem_statement": "...",
      "examples": [
        {"input": "3\\n1 2 3\\n", "output": "6", "explanation": "..."}
      ],
      "constraints": ["1 <= n <= 10^5"],
      "starter_templates": {
        "cpp": "class Solution {\\npublic:\\n    int solve(vector<int>& nums) {\\n        \\n    }\\n};",
        "python": "class Solution:\\n    def solve(self, nums: List[int]) -> int:\\n        pass",
        "java": "class Solution {\\n    public int solve(int[] nums) {\\n        \\n    }\\n}",
        "javascript": "/**\\n * @param {number[]} nums\\n * @return {number}\\n */\\nvar solve = function(nums) {\\n    \\n};"
      },
      "driver_code": {
        "cpp": "int main() { ... }",
        "python": "if __name__ == '__main__': ...",
        "java": "public class Main { ... }",
        "javascript": "const fs = require('fs'); ..."
      },
      "test_cases": [
        {"stdin": "3\\n1 2 3\\n", "expected_output": "6", "is_hidden": false},
        {"stdin": "1\\n5\\n", "expected_output": "5", "is_hidden": false},
        {"stdin": "4\\n-1 2 -3 4\\n", "expected_output": "2", "is_hidden": true},
        {"stdin": "0\\n\\n", "expected_output": "0", "is_hidden": true},
        {"stdin": "5\\n100 200 300 400 500\\n", "expected_output": "1500", "is_hidden": true}
      ]
    }
  ]
}
"""


def _get_top_tags(profile: LeetCodeProfileData) -> Tuple[List[SkillTagStat], List[SkillTagStat], List[SkillTagStat]]:
    """Partitions and sorts candidate tags into Fundamental, Intermediate, and Advanced."""
    fund = sorted(
        [t for t in profile.skill_tags if t.tier == "Fundamental"],
        key=lambda x: x.problems_solved,
        reverse=True,
    )
    inter = sorted(
        [t for t in profile.skill_tags if t.tier == "Intermediate"],
        key=lambda x: x.problems_solved,
        reverse=True,
    )
    adv = sorted(
        [t for t in profile.skill_tags if t.tier == "Advanced"],
        key=lambda x: x.problems_solved,
        reverse=True,
    )

    if not fund:
        fund = [SkillTagStat(tag_name="Array", problems_solved=100, tier="Fundamental")]
    if not inter:
        inter = [SkillTagStat(tag_name="Hash Table", problems_solved=40, tier="Intermediate")]
    if not adv:
        adv = [SkillTagStat(tag_name="Dynamic Programming", problems_solved=30, tier="Advanced")]

    return fund, inter, adv


def _build_user_prompt(
    profile: LeetCodeProfileData,
    num_easy: int,
    num_medium: int,
    num_hard: int,
) -> str:
    fund, inter, adv = _get_top_tags(profile)

    payload = {
        "candidate_username": profile.username,
        "profile_category": profile.category,
        "primary_language": profile.primary_language,
        "total_solved": profile.total_solved,
        "difficulty_distribution": {
            "easy": profile.easy_solved,
            "medium": profile.medium_solved,
            "hard": profile.hard_solved,
        },
        "target_composition": {
            "num_easy": num_easy,
            "num_medium": num_medium,
            "num_hard": num_hard,
            "total_questions": num_easy + num_medium + num_hard,
        },
        "category_1_recent_solved_titles": (
            profile.recent_ac_titles[:15] if profile.category == "PUBLIC_SOLVED_LIST" else []
        ),
        "category_2_tier_breakdown": {
            "top_fundamental_tags": [f"{t.tag_name} (x{t.problems_solved})" for t in fund[:6]],
            "top_intermediate_tags": [f"{t.tag_name} (x{t.problems_solved})" for t in inter[:6]],
            "top_advanced_tags": [f"{t.tag_name} (x{t.problems_solved})" for t in adv[:6]],
        },
    }
    return json.dumps(payload, indent=2)


def _call_gemini_models(system_prompt: str, user_prompt: str) -> Optional[Dict[str, Any]]:
    """
    Calls Gemini API with response_mime_type='application/json' and temperature=0.7.
    Attempts modern google.genai and direct REST across responsive models, logging errors explicitly.
    """
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key or api_key.startswith("your_"):
        logger.error("GEMINI_API_KEY not configured or set to placeholder.")
        return None

    candidate_models = [
        "gemini-3.5-flash-lite",
        "gemini-3.5-flash",
        os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite"),
    ]
    seen_models = set()
    models_to_try = []
    for m in candidate_models:
        if m and m not in seen_models:
            seen_models.add(m)
            models_to_try.append(m)

    # 1. Primary: google.genai SDK (reliable, fast <1s on flash-lite)
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        for model_name in models_to_try:
            try:
                logger.info(f"Attempting OA question generation with google.genai model: {model_name}")
                response = client.models.generate_content(
                    model=model_name,
                    contents=user_prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        response_mime_type="application/json",
                        temperature=0.7,
                    ),
                )
                if response and response.text:
                    clean_text = re.sub(r"^```(?:json)?\s*", "", response.text.strip())
                    clean_text = re.sub(r"\s*```$", "", clean_text)
                    parsed = json.loads(clean_text)
                    if isinstance(parsed, dict) and "oa_questions" in parsed:
                        logger.info(f"Successfully generated OA questions with {model_name}.")
                        return parsed
            except Exception as exc:
                logger.warning(f"google.genai model {model_name} failed: {exc}")
    except Exception as exc:
        logger.warning(f"google.genai initialization error: {exc}")

    # 2. Secondary fallback: Direct REST call via httpx
    try:
        import httpx

        for model_name in models_to_try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
            payload = {
                "systemInstruction": {"parts": [{"text": system_prompt}]},
                "contents": [{"parts": [{"text": user_prompt}]}],
                "generationConfig": {
                    "response_mime_type": "application/json",
                    "temperature": 0.7,
                },
            }
            try:
                logger.info(f"Calling Gemini {model_name} via REST API...")
                resp = httpx.post(url, json=payload, timeout=10.0)
                if resp.status_code == 200:
                    data = resp.json()
                    candidates = data.get("candidates") or []
                    if candidates:
                        text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                        if text:
                            clean_text = re.sub(r"^```(?:json)?\s*", "", text.strip())
                            clean_text = re.sub(r"\s*```$", "", clean_text)
                            parsed = json.loads(clean_text)
                            if isinstance(parsed, dict) and "oa_questions" in parsed:
                                logger.info(f"Direct REST generation succeeded with {model_name}.")
                                return parsed
                else:
                    logger.warning(f"REST {model_name} returned HTTP {resp.status_code}: {resp.text[:200]}")
            except Exception as exc:
                logger.warning(f"REST attempt for {model_name} failed: {exc}")
    except Exception as exc:
        logger.error(f"REST client initialization failed: {exc}")

    return None


def _validate_and_parse_questions(raw_questions: List[Dict[str, Any]]) -> List[OAQuestion]:
    """Validates raw LLM question dictionaries into strict OAQuestion models with stdin/stdout test cases."""
    parsed: List[OAQuestion] = []
    for i, q in enumerate(raw_questions, start=1):
        qid = q.get("question_id") or f"OA-{i}"
        title = q.get("title") or f"Adaptive Assessment Problem {i}"
        diff = q.get("difficulty")
        if diff not in ("Easy", "Medium", "Hard"):
            diff = "Easy" if i == 1 else ("Medium" if i <= 3 else "Hard")

        topics = q.get("topics") or ["Algorithms"]
        reason = q.get("selection_reason") or "Tailored to candidate's verified LeetCode skill telemetry."
        statement = q.get("problem_statement") or "Implement the solution to read from standard input and write to standard output."

        examples_raw = q.get("examples") or []
        examples = [
            OAExample(
                input=str(ex.get("input", "")),
                output=str(ex.get("output", "")),
                explanation=ex.get("explanation"),
            )
            for ex in examples_raw
            if isinstance(ex, dict)
        ]

        constraints = [str(c) for c in (q.get("constraints") or ["1 <= n <= 10^5", "Time limit: 2.0s"])]

        # Parse real test cases
        tc_raw = q.get("test_cases") or []
        test_cases: List[OATestCase] = []
        for tc in tc_raw:
            if isinstance(tc, dict) and "stdin" in tc and "expected_output" in tc:
                test_cases.append(
                    OATestCase(
                        stdin=str(tc["stdin"]),
                        expected_output=str(tc["expected_output"]).strip(),
                        is_hidden=bool(tc.get("is_hidden", False)),
                    )
                )

        # Fallback test cases if LLM omitted them
        if not test_cases:
            if examples:
                test_cases = [
                    OATestCase(stdin=ex.input, expected_output=ex.output, is_hidden=False)
                    for ex in examples
                ]
            else:
                test_cases = [
                    OATestCase(stdin="5\n1 2 3 4 5\n", expected_output="15", is_hidden=False),
                    OATestCase(stdin="1\n42\n", expected_output="42", is_hidden=False),
                    OATestCase(stdin="0\n\n", expected_output="0", is_hidden=True),
                ]

        starter_templates = q.get("starter_templates") or {}
        driver_code = q.get("driver_code") or {}
        if isinstance(driver_code, dict) and "cpp" in driver_code and isinstance(driver_code["cpp"], str):
            driver_code["cpp"] = re.sub(r"^\s*#\s*iostream\b", "#include <iostream>", driver_code["cpp"], flags=re.MULTILINE)
            driver_code["cpp"] = re.sub(r"^\s*#\s*vector\b", "#include <vector>", driver_code["cpp"], flags=re.MULTILINE)
            driver_code["cpp"] = re.sub(r"^\s*#\s*string\b", "#include <string>", driver_code["cpp"], flags=re.MULTILINE)

        # Synthesize fallback class Solution templates if omitted by LLM
        method_name = "".join(
            w.capitalize() if j > 0 else w.lower()
            for j, w in enumerate(re.findall(r"[a-zA-Z0-9]+", title))
        ) or "solve"

        if "cpp" not in starter_templates:
            starter_templates["cpp"] = (
                f"class Solution {{\npublic:\n    // Implement your solution below\n"
                f"    void {method_name}() {{\n        \n    }}\n}};\n"
            )
        if "python" not in starter_templates:
            starter_templates["python"] = (
                f"class Solution:\n    def {method_name}(self):\n        # Implement your solution below\n        pass\n"
            )
        if "java" not in starter_templates:
            starter_templates["java"] = (
                f"class Solution {{\n    public void {method_name}() {{\n        // Implement your solution below\n    }}\n}}\n"
            )
        if "javascript" not in starter_templates:
            starter_templates["javascript"] = (
                f"/**\n * @return {{any}}\n */\nvar {method_name} = function() {{\n    // Implement your solution below\n}};\n"
            )

        parsed.append(
            OAQuestion(
                question_id=qid,
                title=title,
                difficulty=diff,
                topics=topics,
                selection_reason=reason,
                problem_statement=statement,
                examples=examples,
                constraints=constraints,
                starter_code="",  # Empty boilerplate loaded per selected language in workspace
                test_code="",
                test_cases=test_cases,
                starter_templates=starter_templates,
                driver_code=driver_code,
            )
        )
    return parsed


def _generate_dynamic_fallback(
    profile: LeetCodeProfileData,
    num_easy: int = 1,
    num_medium: int = 2,
    num_hard: int = 2,
) -> List[OAQuestion]:
    """
    Synthesizes candidate-specific OA questions strictly tailored to their actual
    username, category, and exact topic counts when offline.
    """
    fund, inter, adv = _get_top_tags(profile)
    top_fund = fund[0].tag_name
    top_fund_count = fund[0].problems_solved
    top_inter = inter[0].tag_name
    top_inter_count = inter[0].problems_solved
    top_adv = adv[0].tag_name
    top_adv_count = adv[0].problems_solved
    second_adv = adv[1].tag_name if len(adv) > 1 else "Backtracking"
    second_adv_count = adv[1].problems_solved if len(adv) > 1 else 15

    username = profile.username
    questions: List[OAQuestion] = []

    # OA-1 (Easy)
    questions.append(
        OAQuestion(
            question_id="OA-1",
            title=f"Distinct Value Distance Filter ({top_fund})",
            difficulty="Easy",
            topics=[top_fund, top_inter],
            selection_reason=(
                f"Generated for @{username} grounded in top Fundamental '{top_fund}' ({top_fund_count} solved) "
                f"and Intermediate '{top_inter}' ({top_inter_count} solved)."
            ),
            problem_statement=(
                f"### Problem Statement\n"
                f"Given an array of integers `nums` and an integer `k`, determine if there exist two distinct indices "
                f"`i` and `j` such that `nums[i] == nums[j]` and `abs(i - j) <= k`.\n\n"
                f"### Input Format\n"
                f"First line: Two space-separated integers `n` and `k`.\n"
                f"Second line: `n` space-separated integers representing `nums`.\n\n"
                f"### Output Format\n"
                f"Print `true` if such a pair exists, otherwise print `false`."
            ),
            examples=[
                OAExample(input="4 3\n1 2 3 1\n", output="true", explanation="nums[0] == nums[3] with index distance 3 <= 3."),
                OAExample(input="6 2\n1 2 3 1 2 3\n", output="false", explanation="Minimum duplicate index distance is 3 > 2."),
            ],
            constraints=["1 <= n <= 10^5", "0 <= k <= 10^5", "-10^9 <= nums[i] <= 10^9"],
            starter_templates={
                "cpp": "class Solution {\npublic:\n    bool containsNearbyDuplicate(vector<int>& nums, int k) {\n        \n    }\n};",
                "python": "class Solution:\n    def containsNearbyDuplicate(self, nums: List[int], k: int) -> bool:\n        pass",
                "java": "class Solution {\n    public boolean containsNearbyDuplicate(int[] nums, int k) {\n        \n    }\n}",
                "javascript": "/**\n * @param {number[]} nums\n * @param {number} k\n * @return {boolean}\n */\nvar containsNearbyDuplicate = function(nums, k) {\n    \n};",
            },
            driver_code={
                "cpp": "int main() {\n    ios::sync_with_stdio(false);\n    cin.tie(nullptr);\n    int n, k;\n    if (!(cin >> n >> k)) return 0;\n    vector<int> nums(n);\n    for (int i = 0; i < n; i++) cin >> nums[i];\n    Solution sol;\n    cout << (sol.containsNearbyDuplicate(nums, k) ? \"true\" : \"false\") << \"\\n\";\n    return 0;\n}",
                "python": "if __name__ == '__main__':\n    import sys\n    tokens = sys.stdin.read().split()\n    if tokens:\n        n = int(tokens[0])\n        k = int(tokens[1])\n        nums = [int(x) for x in tokens[2:2 + n]]\n        sol = Solution()\n        res = sol.containsNearbyDuplicate(nums, k)\n        print('true' if res else 'false')",
                "java": "public class Main {\n    public static void main(String[] args) throws Exception {\n        Scanner sc = new Scanner(System.in);\n        if (!sc.hasNextInt()) return;\n        int n = sc.nextInt();\n        int k = sc.nextInt();\n        int[] nums = new int[n];\n        for (int i = 0; i < n; i++) nums[i] = sc.nextInt();\n        Solution sol = new Solution();\n        boolean res = sol.containsNearbyDuplicate(nums, k);\n        System.out.println(res ? \"true\" : \"false\");\n    }\n}",
                "javascript": "const fs = require('fs');\nconst tokens = fs.readFileSync(0, 'utf-8').trim().split(/\\s+/);\nif (tokens.length >= 2 && tokens[0] !== '') {\n    const n = parseInt(tokens[0], 10);\n    const k = parseInt(tokens[1], 10);\n    const nums = tokens.slice(2, 2 + n).map(Number);\n    const fn = typeof containsNearbyDuplicate === 'function' ? containsNearbyDuplicate : (typeof Solution !== 'undefined' ? new Solution().containsNearbyDuplicate : null);\n    const res = fn ? fn(nums, k) : false;\n    console.log(res ? 'true' : 'false');\n}",
            },
            test_cases=[
                OATestCase(stdin="4 3\n1 2 3 1\n", expected_output="true", is_hidden=False),
                OATestCase(stdin="6 2\n1 2 3 1 2 3\n", expected_output="false", is_hidden=False),
                OATestCase(stdin="1 1\n100\n", expected_output="false", is_hidden=True),
                OATestCase(stdin="5 1\n1 1 2 3 4\n", expected_output="true", is_hidden=True),
                OATestCase(stdin="5 0\n1 1 2 3 4\n", expected_output="false", is_hidden=True),
            ],
        )
    )

    # OA-2 (Medium)
    questions.append(
        OAQuestion(
            question_id="OA-2",
            title=f"Target Subarray Sum Partition ({top_inter} & {top_adv})",
            difficulty="Medium",
            topics=[top_inter, top_adv],
            selection_reason=(
                f"Synthesized for @{username} combining Intermediate '{top_inter}' ({top_inter_count} solved) "
                f"and Advanced '{top_adv}' ({top_adv_count} solved)."
            ),
            problem_statement=(
                f"### Problem Statement\n"
                f"Given an integer array `nums` and an integer `k`, find the total number of continuous subarrays "
                f"whose sum equals `k` and whose subarray length is an even number.\n\n"
                f"### Input Format\n"
                f"First line: Two space-separated integers `n` and `k`.\n"
                f"Second line: `n` space-separated integers representing `nums`.\n\n"
                f"### Output Format\n"
                f"Print a single integer: the count of qualifying subarrays."
            ),
            examples=[
                OAExample(input="5 3\n1 2 1 2 1\n", output="2", explanation="Subarrays [1, 2] and [2, 1] both sum to 3 and have even length 2."),
                OAExample(input="3 2\n1 1 1\n", output="2", explanation="[1, 1] at indices [0, 1] and [1, 2] are valid."),
            ],
            constraints=["1 <= n <= 2 * 10^4", "-1000 <= nums[i] <= 1000", "-10^7 <= k <= 10^7"],
            starter_templates={
                "cpp": "class Solution {\npublic:\n    int subarraySumEven(vector<int>& nums, int k) {\n        \n    }\n};",
                "python": "class Solution:\n    def subarraySumEven(self, nums: List[int], k: int) -> int:\n        pass",
                "java": "class Solution {\n    public int subarraySumEven(int[] nums, int k) {\n        \n    }\n}",
                "javascript": "/**\n * @param {number[]} nums\n * @param {number} k\n * @return {number}\n */\nvar subarraySumEven = function(nums, k) {\n    \n};",
            },
            driver_code={
                "cpp": "int main() {\n    ios::sync_with_stdio(false);\n    cin.tie(nullptr);\n    int n, k;\n    if (!(cin >> n >> k)) return 0;\n    vector<int> nums(n);\n    for (int i = 0; i < n; i++) cin >> nums[i];\n    Solution sol;\n    cout << sol.subarraySumEven(nums, k) << \"\\n\";\n    return 0;\n}",
                "python": "if __name__ == '__main__':\n    import sys\n    tokens = sys.stdin.read().split()\n    if tokens:\n        n = int(tokens[0])\n        k = int(tokens[1])\n        nums = [int(x) for x in tokens[2:2 + n]]\n        sol = Solution()\n        print(sol.subarraySumEven(nums, k))",
                "java": "public class Main {\n    public static void main(String[] args) throws Exception {\n        Scanner sc = new Scanner(System.in);\n        if (!sc.hasNextInt()) return;\n        int n = sc.nextInt();\n        int k = sc.nextInt();\n        int[] nums = new int[n];\n        for (int i = 0; i < n; i++) nums[i] = sc.nextInt();\n        Solution sol = new Solution();\n        System.out.println(sol.subarraySumEven(nums, k));\n    }\n}",
                "javascript": "const fs = require('fs');\nconst tokens = fs.readFileSync(0, 'utf-8').trim().split(/\\s+/);\nif (tokens.length >= 2 && tokens[0] !== '') {\n    const n = parseInt(tokens[0], 10);\n    const k = parseInt(tokens[1], 10);\n    const nums = tokens.slice(2, 2 + n).map(Number);\n    const fn = typeof subarraySumEven === 'function' ? subarraySumEven : (typeof Solution !== 'undefined' ? new Solution().subarraySumEven : null);\n    console.log(fn ? fn(nums, k) : 0);\n}",
            },
            test_cases=[
                OATestCase(stdin="5 3\n1 2 1 2 1\n", expected_output="2", is_hidden=False),
                OATestCase(stdin="3 2\n1 1 1\n", expected_output="2", is_hidden=False),
                OATestCase(stdin="1 5\n5\n", expected_output="0", is_hidden=True),
                OATestCase(stdin="4 0\n0 0 0 0\n", expected_output="4", is_hidden=True),
                OATestCase(stdin="6 6\n1 2 3 3 2 1\n", expected_output="1", is_hidden=True),
            ],
        )
    )

    # OA-3 (Medium)
    questions.append(
        OAQuestion(
            question_id="OA-3",
            title=f"Maximum Subarray Flow with Capacity Constraints ({top_adv})",
            difficulty="Medium",
            topics=[top_adv, "Sliding Window"],
            selection_reason=(
                f"Stress-tests candidate's claimed competency in '{top_adv}' ({top_adv_count} solved)."
            ),
            problem_statement=(
                f"### Problem Statement\n"
                f"Given an array `nums` and an integer `limit`, find the length of the longest non-empty subarray "
                f"such that the absolute difference between any two elements of this subarray is less than or equal to `limit`.\n\n"
                f"### Input Format\n"
                f"First line: Two space-separated integers `n` and `limit`.\n"
                f"Second line: `n` space-separated integers representing `nums`.\n\n"
                f"### Output Format\n"
                f"Print a single integer representing the maximum subarray length."
            ),
            examples=[
                OAExample(input="4 4\n8 2 4 7\n", output="2", explanation="Longest valid subarray is [2, 4] with difference 2 <= 4."),
                OAExample(input="6 5\n10 1 2 4 7 2\n", output="4", explanation="Subarray [2, 4, 7, 2] has max-min = 7-2 = 5 <= 5."),
            ],
            constraints=["1 <= n <= 10^5", "1 <= nums[i] <= 10^9", "0 <= limit <= 10^9"],
            starter_templates={
                "cpp": "class Solution {\npublic:\n    int longestSubarray(vector<int>& nums, int limit) {\n        \n    }\n};",
                "python": "class Solution:\n    def longestSubarray(self, nums: List[int], limit: int) -> int:\n        pass",
                "java": "class Solution {\n    public int longestSubarray(int[] nums, int limit) {\n        \n    }\n}",
                "javascript": "/**\n * @param {number[]} nums\n * @param {number} limit\n * @return {number}\n */\nvar longestSubarray = function(nums, limit) {\n    \n};",
            },
            driver_code={
                "cpp": "int main() {\n    ios::sync_with_stdio(false);\n    cin.tie(nullptr);\n    int n, limit;\n    if (!(cin >> n >> limit)) return 0;\n    vector<int> nums(n);\n    for (int i = 0; i < n; i++) cin >> nums[i];\n    Solution sol;\n    cout << sol.longestSubarray(nums, limit) << \"\\n\";\n    return 0;\n}",
                "python": "if __name__ == '__main__':\n    import sys\n    tokens = sys.stdin.read().split()\n    if tokens:\n        n = int(tokens[0])\n        limit = int(tokens[1])\n        nums = [int(x) for x in tokens[2:2 + n]]\n        sol = Solution()\n        print(sol.longestSubarray(nums, limit))",
                "java": "public class Main {\n    public static void main(String[] args) throws Exception {\n        Scanner sc = new Scanner(System.in);\n        if (!sc.hasNextInt()) return;\n        int n = sc.nextInt();\n        int limit = sc.nextInt();\n        int[] nums = new int[n];\n        for (int i = 0; i < n; i++) nums[i] = sc.nextInt();\n        Solution sol = new Solution();\n        System.out.println(sol.longestSubarray(nums, limit));\n    }\n}",
                "javascript": "const fs = require('fs');\nconst tokens = fs.readFileSync(0, 'utf-8').trim().split(/\\s+/);\nif (tokens.length >= 2 && tokens[0] !== '') {\n    const n = parseInt(tokens[0], 10);\n    const limit = parseInt(tokens[1], 10);\n    const nums = tokens.slice(2, 2 + n).map(Number);\n    const fn = typeof longestSubarray === 'function' ? longestSubarray : (typeof Solution !== 'undefined' ? new Solution().longestSubarray : null);\n    console.log(fn ? fn(nums, limit) : 0);\n}",
            },
            test_cases=[
                OATestCase(stdin="4 4\n8 2 4 7\n", expected_output="2", is_hidden=False),
                OATestCase(stdin="6 5\n10 1 2 4 7 2\n", expected_output="4", is_hidden=False),
                OATestCase(stdin="1 0\n5\n", expected_output="1", is_hidden=True),
                OATestCase(stdin="5 0\n3 3 3 3 3\n", expected_output="5", is_hidden=True),
                OATestCase(stdin="5 2\n1 5 9 13 17\n", expected_output="1", is_hidden=True),
            ],
        )
    )

    # OA-4 (Hard)
    questions.append(
        OAQuestion(
            question_id="OA-4",
            title=f"Optimal Redundant Edge Removal in Cycle ({second_adv})",
            difficulty="Hard",
            topics=[second_adv, "Graph", "Union-Find"],
            selection_reason=(
                f"Stress-tests @{username}'s claimed Advanced '{second_adv}' skill ({second_adv_count} solved)."
            ),
            problem_statement=(
                f"### Problem Statement\n"
                f"Given an undirected graph with `n` vertices labeled 1 to `n` and `n` edges, find an edge that can be "
                f"removed so that the resulting graph is a tree of `n` nodes. If there are multiple answers, return the edge "
                f"that occurs last in the input.\n\n"
                f"### Input Format\n"
                f"First line: Integer `n` representing number of vertices/edges.\n"
                f"Next `n` lines: Two space-separated integers `u` and `v` representing an edge.\n\n"
                f"### Output Format\n"
                f"Print two space-separated integers representing the redundant edge."
            ),
            examples=[
                OAExample(input="3\n1 2\n1 3\n2 3\n", output="2 3", explanation="Edge [2, 3] creates the cycle."),
                OAExample(input="5\n1 2\n2 3\n3 4\n1 4\n1 5\n", output="1 4", explanation="Edge [1, 4] completes redundant cycle."),
            ],
            constraints=["3 <= n <= 1000", "1 <= u < v <= n"],
            starter_templates={
                "cpp": "class Solution {\npublic:\n    vector<int> findRedundantConnection(vector<vector<int>>& edges) {\n        \n    }\n};",
                "python": "class Solution:\n    def findRedundantConnection(self, edges: List[List[int]]) -> List[int]:\n        pass",
                "java": "class Solution {\n    public int[] findRedundantConnection(int[][] edges) {\n        \n    }\n}",
                "javascript": "/**\n * @param {number[][]} edges\n * @return {number[]}\n */\nvar findRedundantConnection = function(edges) {\n    \n};",
            },
            driver_code={
                "cpp": "int main() {\n    ios::sync_with_stdio(false);\n    cin.tie(nullptr);\n    int n;\n    if (!(cin >> n)) return 0;\n    vector<vector<int>> edges(n, vector<int>(2));\n    for (int i = 0; i < n; i++) cin >> edges[i][0] >> edges[i][1];\n    Solution sol;\n    vector<int> res = sol.findRedundantConnection(edges);\n    if (res.size() >= 2) cout << res[0] << \" \" << res[1] << \"\\n\";\n    return 0;\n}",
                "python": "if __name__ == '__main__':\n    import sys\n    tokens = sys.stdin.read().split()\n    if tokens:\n        n = int(tokens[0])\n        edges = []\n        idx = 1\n        for _ in range(n):\n            edges.append([int(tokens[idx]), int(tokens[idx + 1])])\n            idx += 2\n        sol = Solution()\n        res = sol.findRedundantConnection(edges)\n        print(f\"{res[0]} {res[1]}\")",
                "java": "public class Main {\n    public static void main(String[] args) throws Exception {\n        Scanner sc = new Scanner(System.in);\n        if (!sc.hasNextInt()) return;\n        int n = sc.nextInt();\n        int[][] edges = new int[n][2];\n        for (int i = 0; i < n; i++) { edges[i][0] = sc.nextInt(); edges[i][1] = sc.nextInt(); }\n        Solution sol = new Solution();\n        int[] res = sol.findRedundantConnection(edges);\n        System.out.println(res[0] + \" \" + res[1]);\n    }\n}",
                "javascript": "const fs = require('fs');\nconst tokens = fs.readFileSync(0, 'utf-8').trim().split(/\\s+/);\nif (tokens.length >= 1 && tokens[0] !== '') {\n    const n = parseInt(tokens[0], 10);\n    const edges = [];\n    let idx = 1;\n    for (let i = 0; i < n; i++) { edges.push([Number(tokens[idx]), Number(tokens[idx + 1])]); idx += 2; }\n    const fn = typeof findRedundantConnection === 'function' ? findRedundantConnection : (typeof Solution !== 'undefined' ? new Solution().findRedundantConnection : null);\n    const res = fn ? fn(edges) : [0, 0];\n    console.log(`${res[0]} ${res[1]}`);\n}",
            },
            test_cases=[
                OATestCase(stdin="3\n1 2\n1 3\n2 3\n", expected_output="2 3", is_hidden=False),
                OATestCase(stdin="5\n1 2\n2 3\n3 4\n1 4\n1 5\n", expected_output="1 4", is_hidden=False),
                OATestCase(stdin="4\n1 2\n2 3\n3 4\n1 4\n", expected_output="1 4", is_hidden=True),
                OATestCase(stdin="4\n1 2\n1 3\n1 4\n2 3\n", expected_output="2 3", is_hidden=True),
                OATestCase(stdin="3\n1 2\n2 3\n1 3\n", expected_output="1 3", is_hidden=True),
            ],
        )
    )

    # OA-5 (Hard)
    questions.append(
        OAQuestion(
            question_id="OA-5",
            title=f"Constrained Sequence Permutation Inversions ({top_adv})",
            difficulty="Hard",
            topics=[top_adv, "Combinatorics"],
            selection_reason=(
                f"Peak stress-test evaluating candidate's mastery in '{top_adv}' ({top_adv_count} solved)."
            ),
            problem_statement=(
                f"### Problem Statement\n"
                f"For integers `n` and `k`, count the number of different permutations of numbers from 1 to `n` "
                f"such that there are exactly `k` inverse pairs. Print the result modulo 10^9 + 7.\n\n"
                f"### Input Format\n"
                f"Single line with two space-separated integers `n` and `k`.\n\n"
                f"### Output Format\n"
                f"Print a single integer: the count of valid permutations modulo 10^9 + 7."
            ),
            examples=[
                OAExample(input="3 0\n", output="1", explanation="Only [1, 2, 3] has 0 inverse pairs."),
                OAExample(input="3 1\n", output="2", explanation="[1, 3, 2] and [2, 1, 3] each have 1 inverse pair."),
            ],
            constraints=["1 <= n <= 1000", "0 <= k <= 1000"],
            starter_templates={
                "cpp": "class Solution {\npublic:\n    int kInversePairs(int n, int k) {\n        \n    }\n};",
                "python": "class Solution:\n    def kInversePairs(self, n: int, k: int) -> int:\n        pass",
                "java": "class Solution {\n    public int kInversePairs(int n, int k) {\n        \n    }\n}",
                "javascript": "/**\n * @param {number} n\n * @param {number} k\n * @return {number}\n */\nvar kInversePairs = function(n, k) {\n    \n};",
            },
            driver_code={
                "cpp": "int main() {\n    ios::sync_with_stdio(false);\n    cin.tie(nullptr);\n    int n, k;\n    if (!(cin >> n >> k)) return 0;\n    Solution sol;\n    cout << sol.kInversePairs(n, k) << \"\\n\";\n    return 0;\n}",
                "python": "if __name__ == '__main__':\n    import sys\n    tokens = sys.stdin.read().split()\n    if tokens:\n        n = int(tokens[0])\n        k = int(tokens[1])\n        sol = Solution()\n        print(sol.kInversePairs(n, k))",
                "java": "public class Main {\n    public static void main(String[] args) throws Exception {\n        Scanner sc = new Scanner(System.in);\n        if (!sc.hasNextInt()) return;\n        int n = sc.nextInt();\n        int k = sc.nextInt();\n        Solution sol = new Solution();\n        System.out.println(sol.kInversePairs(n, k));\n    }\n}",
                "javascript": "const fs = require('fs');\nconst tokens = fs.readFileSync(0, 'utf-8').trim().split(/\\s+/);\nif (tokens.length >= 2 && tokens[0] !== '') {\n    const n = parseInt(tokens[0], 10);\n    const k = parseInt(tokens[1], 10);\n    const fn = typeof kInversePairs === 'function' ? kInversePairs : (typeof Solution !== 'undefined' ? new Solution().kInversePairs : null);\n    console.log(fn ? fn(n, k) : 0);\n}",
            },
            test_cases=[
                OATestCase(stdin="3 0\n", expected_output="1", is_hidden=False),
                OATestCase(stdin="3 1\n", expected_output="2", is_hidden=False),
                OATestCase(stdin="1 0\n", expected_output="1", is_hidden=True),
                OATestCase(stdin="3 3\n", expected_output="1", is_hidden=True),
                OATestCase(stdin="4 2\n", expected_output="5", is_hidden=True),
            ],
        )
    )

    return questions


async def generate_oa_questions(
    profile: LeetCodeProfileData,
    num_easy: int = 1,
    num_medium: int = 2,
    num_hard: int = 2,
) -> List[OAQuestion]:
    """
    Main entrypoint for dynamic LeetCode OA Generation.
    Calls Gemini 2.5/3.5 Flash with strict JSON schema enforcing 5 tailored questions.
    """
    total_requested = num_easy + num_medium + num_hard
    user_prompt = _build_user_prompt(profile, num_easy, num_medium, num_hard)

    logger.info(
        f"Generating live OA questions for @{profile.username} (Category: {profile.category}, Solved: {profile.total_solved})"
    )

    # 1. Attempt dynamic Gemini LLM generation
    try:
        llm_out = _call_gemini_models(OA_SYSTEM_PROMPT, user_prompt)
        if llm_out and isinstance(llm_out, dict):
            raw_qs = llm_out.get("oa_questions")
            if isinstance(raw_qs, list) and len(raw_qs) >= total_requested:
                parsed = _validate_and_parse_questions(raw_qs[:total_requested])
                logger.info(f"Successfully generated {len(parsed)} unique questions via Gemini for @{profile.username}.")
                return parsed
            else:
                logger.warning(f"Gemini returned incomplete question list: {len(raw_qs) if isinstance(raw_qs, list) else 0}")
    except Exception as exc:
        logger.error(f"Gemini live OA generation encountered error: {exc}", exc_info=True)

    # 2. Candidate-specific dynamic fallback (not static generic questions)
    logger.info(f"Using candidate-parameterized dynamic generator for @{profile.username}.")
    return _generate_dynamic_fallback(profile, num_easy, num_medium, num_hard)
