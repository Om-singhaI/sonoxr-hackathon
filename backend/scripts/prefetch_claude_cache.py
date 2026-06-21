#!/usr/bin/env python3
"""
prefetch_claude_cache.py
Pre-fetches Claude AI responses for all CAMUS patients and all 4 preset queries,
saving results to unity/SonoXR_Quest3/Assets/StreamingAssets/claude_cache/

Usage:
    ANTHROPIC_API_KEY=sk-ant-... python scripts/prefetch_claude_cache.py
    ANTHROPIC_API_KEY=sk-ant-... python scripts/prefetch_claude_cache.py --force
"""

import os
import sys
import json
import time
import argparse
from pathlib import Path

try:
    import anthropic
except ImportError:
    print("ERROR: 'anthropic' package not found. Install with: pip install anthropic")
    sys.exit(1)

# ── Paths ─────────────────────────────────────────────────────────────────────

REPO_ROOT   = Path(__file__).parent.parent
BUNDLE_DIR  = REPO_ROOT / "frontend" / "patient_bundles"
CACHE_DIR   = REPO_ROOT / "unity" / "SonoXR_Quest3" / "Assets" / "StreamingAssets" / "claude_cache"

# ── Prompts (mirrors ClaudeAgentPanel.cs) ─────────────────────────────────────

SYSTEM_PROMPT = (
    "You are an AI assistant for SonoXR, a research demonstration of ultrasound-derived 3D cardiac reconstruction. "
    "Rules: (1) Explain in plain language for educated non-specialists. "
    "(2) NEVER diagnose or make clinical recommendations. "
    "(3) ALWAYS flag that EF is a biplane geometric estimate, not a precision clinical measurement. "
    "(4) ALWAYS mention low-confidence regions when relevant. "
    "(5) NEVER invent anatomy or measurements beyond what is provided. "
    "(6) State data is from CAMUS dataset (real patients, not live scanning). "
    "(7) Keep responses to 4-6 sentences. "
    '(8) End every response with: "This is a research demonstration only — not a clinical assessment."'
)


def build_prompts(meta: dict) -> list[str]:
    """Build the 4 preset prompts for a patient — mirrors ClaudeAgentPanel.Prompts()."""
    ef       = meta.get("EF_pct", 0)
    edv      = meta.get("EDV_mL", 0)
    esv      = meta.get("ESV_mL", 0)
    quality  = meta.get("image_quality", "unknown")
    unc      = meta.get("uncertainty_region") or {}
    unc_name = unc.get("region_name", "basal")
    unc_rsn  = unc.get("reason", "limited acoustic window in apical views")

    return [
        (
            f"Explain what the 3D reconstruction of this patient's left ventricle tells us. "
            f"EF={ef:.0f}%, EDV={edv:.0f}mL, ESV={esv:.0f}mL, quality={quality}. "
            f"Uncertainty in {unc_name}: {unc_rsn}"
        ),
        (
            "In plain language, what does ejection fraction measure and why does it matter "
            "for understanding heart function?"
        ),
        (
            f"Why is the {unc_name} region uncertain "
            f"in apical ultrasound reconstructions? Explain for a non-specialist. "
            f"Context: {unc_rsn}"
        ),
        (
            f"This patient has EF={ef:.0f}%. Is this normal, mildly reduced, or severely reduced "
            f"by standard clinical thresholds, and what does that typically indicate about cardiac function?"
        ),
    ]


# ── API call ──────────────────────────────────────────────────────────────────

def call_claude(client: anthropic.Anthropic, system: str, user: str) -> str:
    """Call the Anthropic API and return the response text."""
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=400,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    # Extract text from the first content block
    for block in message.content:
        if block.type == "text":
            return block.text
    raise ValueError("No text content in API response")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Pre-fetch Claude cache for SonoXR")
    parser.add_argument("--force", action="store_true",
                        help="Re-fetch even if cache file already exists")
    args = parser.parse_args()

    # API key
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key or not api_key.startswith("sk-ant"):
        print("ERROR: Set ANTHROPIC_API_KEY environment variable to your Anthropic API key.")
        print("  export ANTHROPIC_API_KEY=sk-ant-...")
        sys.exit(1)

    # Verify bundle dir
    index_path = BUNDLE_DIR / "index.json"
    if not index_path.exists():
        print(f"ERROR: index.json not found at {index_path}")
        print("  Run the bundle build script first: python scripts/build_camus_bundle.py")
        sys.exit(1)

    with open(index_path) as f:
        index = json.load(f)

    patients = index.get("patients", [])
    if not patients:
        print("ERROR: No patients listed in index.json")
        sys.exit(1)

    print(f"Found {len(patients)} patient(s): {', '.join(patients)}")

    # Create cache dir
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Cache directory: {CACHE_DIR}")

    # Init Anthropic client
    client = anthropic.Anthropic(api_key=api_key)

    total_queries   = len(patients) * 4
    completed       = 0
    skipped         = 0
    failed          = 0

    for pid in patients:
        meta_path = BUNDLE_DIR / pid / "meta.json"
        if not meta_path.exists():
            print(f"\n[{pid}] SKIP — meta.json not found at {meta_path}")
            failed += 4
            continue

        with open(meta_path) as f:
            meta = json.load(f)

        prompts = build_prompts(meta)
        print(f"\n[{pid}]  EF={meta.get('EF_pct', '?'):.0f}%  quality={meta.get('image_quality', '?')}")

        for q_idx, prompt in enumerate(prompts):
            cache_file = CACHE_DIR / f"{pid}_q{q_idx}.txt"

            if cache_file.exists() and not args.force:
                print(f"  q{q_idx}: SKIP (cached) — {cache_file.name}")
                skipped += 1
                continue

            print(f"  q{q_idx}: Fetching ...", end="", flush=True)
            try:
                response = call_claude(client, SYSTEM_PROMPT, prompt)
                cache_file.write_text(response, encoding="utf-8")
                print(f" OK ({len(response)} chars)")
                completed += 1
                # Be polite to the API — avoid burst rate-limiting
                time.sleep(0.5)
            except anthropic.RateLimitError:
                print(" RATE LIMITED — waiting 20s ...")
                time.sleep(20)
                try:
                    response = call_claude(client, SYSTEM_PROMPT, prompt)
                    cache_file.write_text(response, encoding="utf-8")
                    print(f"  q{q_idx}: OK after retry ({len(response)} chars)")
                    completed += 1
                except Exception as e2:
                    print(f"  q{q_idx}: FAILED after retry — {e2}")
                    failed += 1
            except Exception as e:
                print(f" FAILED — {e}")
                failed += 1

    print(f"\n── Summary ──────────────────────────────────────")
    print(f"  Total queries : {total_queries}")
    print(f"  Fetched       : {completed}")
    print(f"  Skipped (cached): {skipped}")
    print(f"  Failed        : {failed}")
    print(f"  Cache dir     : {CACHE_DIR}")
    if failed:
        print(f"\nWARNING: {failed} queries failed. Re-run to retry.")
        sys.exit(1)


if __name__ == "__main__":
    main()
