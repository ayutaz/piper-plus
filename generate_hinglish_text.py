#!/usr/bin/env python3
"""
generate_hinglish_text.py

Generates conversational, Latin-script Hinglish programming tutor dialogue lines
using DeepSeek API (OpenAI-compatible) and saves to Piper-compatible metadata format.

Usage:
  .venv/bin/python generate_hinglish_text.py
"""

import asyncio
import json
import os
from pathlib import Path
import re
import sys
from typing import List, Literal

from openai import AsyncOpenAI
from pydantic import BaseModel, Field


def load_env_file(env_path: Path | str = ".env") -> None:
    """Loads key-value pairs from .env file into os.environ if not already set."""
    p = Path(env_path)
    if not p.exists():
        return
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip("'\"")
            if key and val:
                os.environ[key] = val


# Load .env file automatically
load_env_file()


class TrainingUtterance(BaseModel):
    text: str = Field(
        description="Conversational Hinglish tutor text using ONLY Latin/English characters (A-Z, a-z)."
    )
    expression: Literal[
        "encouraging", "supportive", "neutral", "call_to_action", "instructive"
    ] = Field(
        description="Pedagogical tone of the tutor."
    )


class DialogueBatch(BaseModel):
    utterances: List[TrainingUtterance]


def clean_json_response(raw_text: str) -> str:
    """Strips markdown code fence blocks if returned by the LLM."""
    raw_text = raw_text.strip()
    if raw_text.startswith("```"):
        raw_text = re.sub(r"^```[a-zA-Z]*\n", "", raw_text)
        raw_text = re.sub(r"\n```$", "", raw_text)
    return raw_text.strip()


async def generate_batch_async(
    client: AsyncOpenAI, batch_id: int, topic: str, max_retries: int = 3
) -> List[TrainingUtterance]:
    """Generates pure Latin-script Hinglish tutor lines using DeepSeek with retries."""
    prompt = f"""
You are an expert synthetic data generator for an Indian AI Programming Tutor.
Generate exactly 10 distinct, natural dialogue lines a tutor would say to a student.

Current Target Focus Area: {topic}

CRITICAL RULES:
1. SCRIPT RESTRICTION: Use STRICTLY Latin characters (A-Z, a-z) and basic punctuation (. , ! ? -).
   ABSOLUTELY NO DEVANAGARI CHARACTERS (e.g., no क, ख, ग, 1, 2, ३).
2. LANGUAGE: Natural conversational Hinglish (blend of spoken Hindi in English script + English coding terms).
   Example: 'Yeh loop infinitely execute ho raha hai kyunki counter update nahi hua.'
3. NUMBER EXPANSION: Never use digits like 1, 10, 42. Spell them phonetically in words ('ek', 'dus', 'chalis').
4. STANDARDIZED PHONETICS: Use standard spellings like 'mein' (not men), 'hai' (not hay), 'achha' (not acha), 'kya' (not kyah).
5. LENGTH: 20 to 35 words per line (~10-15 seconds of spoken audio).
6. TONE: Indian coding teacher—warm, encouraging, instructive.

Return ONLY a valid JSON object matching this schema:
{{
  "utterances": [
    {{
      "text": "Aapka syntax bilkul sahi hai, bas function call karte waqt brackets lagana bhool gaye the.",
      "expression": "instructive"
    }}
  ]
}}
"""
    for attempt in range(1, max_retries + 1):
        try:
            response = await client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a specialized TTS dataset generator that outputs strictly structured JSON.",
                    },
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.7,
            )

            raw_content = clean_json_response(response.choices[0].message.content or "")
            data = DialogueBatch.model_validate_json(raw_content)
            print(f"[Batch {batch_id + 1}] Successfully generated {len(data.utterances)} lines for: '{topic}'")
            return data.utterances
        except Exception as e:
            print(f"[Batch {batch_id + 1}] Attempt {attempt}/{max_retries} error: {e}", file=sys.stderr)
            if attempt < max_retries:
                await asyncio.sleep(2 * attempt)

    print(f"[Batch {batch_id + 1}] Failed after {max_retries} attempts for topic: '{topic}'", file=sys.stderr)
    return []


async def main():
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key or api_key == "your-deepseek-api-key":
        print(
            "ERROR: DEEPSEEK_API_KEY is not set or empty!\n"
            "Please add your key in the .env file:\n"
            "  DEEPSEEK_API_KEY=sk-...\n"
            "or set it in your terminal:\n"
            "  export DEEPSEEK_API_KEY='sk-...'\n",
            file=sys.stderr,
        )
        sys.exit(1)

    client = AsyncOpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com",
    )

    topics = [
        "Debugging a syntax error and indentation",
        "Explaining for-loops versus while-loops",
        "Praising a student for fixing their logic error",
        "Guiding a student stuck on list indexing and slicing",
        "Explaining variables, functions, and return statements",
        "Introducing classes and object-oriented basics",
        "Encouraging a frustrated student who wants to quit",
        "Giving a hint for a palindrome or recursion problem",
        "Explaining async-await and promises simply",
        "Handling edge cases and zero division errors",
    ]

    print(f"Starting concurrent generation for {len(topics)} batches using DeepSeek...")
    tasks = [generate_batch_async(client, i, topic) for i, topic in enumerate(topics)]
    results = await asyncio.gather(*tasks)

    all_records = []
    for batch_result in results:
        all_records.extend(batch_result)

    if not all_records:
        print("No records generated. Please check your API key and network connection.", file=sys.stderr)
        return

    output_dir = Path("dataset_output")
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Save Piper-compatible format: file_id|text
    metadata_txt = output_dir / "metadata.txt"
    with open(metadata_txt, "w", encoding="utf-8") as f:
        for idx, record in enumerate(all_records, 1):
            file_id = f"hinglish_{idx:04d}"
            f.write(f"{file_id}|{record.text}\n")

    # 2. Also save full JSON records (with expressions)
    metadata_json = output_dir / "metadata.json"
    with open(metadata_json, "w", encoding="utf-8") as f:
        json.dump([r.model_dump() for r in all_records], f, ensure_ascii=False, indent=2)

    print(f"\n[DONE] Successfully generated and saved {len(all_records)} lines:")
    print(f"  - Piper Metadata: {metadata_txt.resolve()}")
    print(f"  - Structured JSON: {metadata_json.resolve()}")


if __name__ == "__main__":
    asyncio.run(main())
