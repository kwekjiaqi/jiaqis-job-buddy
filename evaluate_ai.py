"""Optional provider API evaluation on the existing synthetic labels.

Run with GEMINI_API_KEY in your environment: python evaluate_ai.py --provider Gemini --split development
Run holdout separately after development: python evaluate_ai.py --split holdout
Do not tune the prompt against holdout outputs.
"""

import argparse
import json
import os
from pathlib import Path

from ai_review import review_role


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=["development", "holdout"], required=True)
    parser.add_argument("--provider", choices=["Gemini", "OpenAI"], default="Gemini")
    args = parser.parse_args()
    env_name = "GEMINI_API_KEY" if args.provider == "Gemini" else "OPENAI_API_KEY"
    key = os.environ.get(env_name, "")
    if not key:
        parser.error(f"Set {env_name} in your local environment first; never put it in GitHub.")
    cases = json.loads((Path(__file__).parent / "tests" / f"{args.split}.json").read_text())
    correct = 0
    for case in cases:
        job = {"title": case["title"], "company": "Fixture Co", "location": "Singapore",
               "salary": case["salary"], "description": case["description"]}
        preferences = {"target_function": "consultant", "target_domain": "AI", "years_experience": case["years"],
                       "minimum_annual_pay": case["minimum_usd"], "currency": "USD", "target_city": "Singapore",
                       "remote_allowed": False}
        # Assess the model without the rule-based Skip clamp; exact-quote checks still apply.
        result = review_role(key, case["cv"], job, preferences, "Review", provider=args.provider)
        correct += result["decision"] == case["expected"]
        print(f"{case['name']}: expected {case['expected']}, model suggestion {result['decision']}, "
              f"guardrail flags {len(result['flags'])}")
    print(f"{args.split}: {correct}/{len(cases)} agreement with synthetic human labels; no real-world accuracy claim")


if __name__ == "__main__":
    main()
