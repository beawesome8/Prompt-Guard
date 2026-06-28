"""
Loads the v1 prompt, calls Claude, validates the response against the CRM schema.
Run this to confirm Phase 1 is working before proceeding.
"""

import json
import os
import sys
import yaml
from typing import Any

import anthropic
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from evals.schemas.crm_output_schema import CRMSummary
from pydantic import ValidationError

load_dotenv()


def load_prompt(path: str) -> dict:
    """Loads a prompt YAML file and returns it as a dictionary."""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_messages(prompt_config: dict, user_input: str) -> tuple[list[dict[str, Any]], str]:
    """Builds the messages list for the Anthropic API call."""
    few_shot = ""
    for example in prompt_config.get("few_shot_examples", []):
        few_shot += f"\nInput: {example['input']}\nOutput: {example['output']}\n"

    system = prompt_config["system_prompt"]
    if few_shot:
        system += f"\n\nExamples:{few_shot}"

    return [
        {"role": "user", "content": f"Customer note: {user_input}"}
    ], system


def call_claude(prompt_config: dict, user_input: str) -> dict:
    """Calls the Anthropic API and returns raw response text plus token usage."""
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    messages, system = build_messages(prompt_config, user_input)

    response = client.messages.create(
        model=prompt_config["model"]["model_id"],
        max_tokens=prompt_config["model"]["max_tokens"],
        temperature=prompt_config["model"]["temperature"],
        system=system,
        messages=messages,  # type: ignore
    )

    # Extract text from response content
    text_content = response.content[0]
    raw_text = text_content.text if hasattr(text_content, 'text') else str(text_content)  # type: ignore
    
    return {
        "raw_text": raw_text,
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }


def validate_output(raw_text: str) -> tuple[bool, CRMSummary | None, str]:
    """Parses and validates raw model output against the CRM schema."""
    try:
        cleaned = raw_text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1]
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("```", 1)[0]
        cleaned = cleaned.strip()

        parsed = json.loads(cleaned)
        validated = CRMSummary(**parsed)
        return True, validated, ""
    except json.JSONDecodeError as e:
        return False, None, f"JSON parse error: {e}"
    except ValidationError as e:
        return False, None, f"Schema validation error: {e}"


def run_test():
    """Runs a single end-to-end test of the CRM summary feature."""
    prompt_path = "prompts/crm_summary_v1.yaml"
    test_input = "hi ive been waiting 3 weeks for my order where is it?? this is ridiculous"

    print("=" * 60)
    print("PromptGuard — Phase 1 Feature Test")
    print("=" * 60)
    print(f"Prompt file : {prompt_path}")
    print(f"Test input  : {test_input}")
    print("-" * 60)

    prompt_config = load_prompt(prompt_path)
    result = call_claude(prompt_config, test_input)

    print(f"Raw output  : {result['raw_text']}")
    print(f"Tokens used : {result['input_tokens']} in / {result['output_tokens']} out")
    print("-" * 60)

    valid, parsed, error = validate_output(result["raw_text"])

    if valid and parsed:
        print("Schema validation : PASSED")
        print(f"Summary    : {parsed.summary}")
        print(f"Sentiment  : {parsed.sentiment}")
        print(f"Next action: {parsed.next_action}")
        print(f"Urgency    : {parsed.urgency}")
        print(f"Confidence : {parsed.confidence}")
    else:
        print(f"Schema validation : FAILED")
        print(f"Error: {error}")

    print("=" * 60)


if __name__ == "__main__":
    run_test()