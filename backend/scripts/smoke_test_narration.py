#!/usr/bin/env python3
"""One-command proof that the LIVE AI narration works (FIX 4).

Confirms REAL_AI mode end to end before judging:
  * loads ANTHROPIC_API_KEY (from the environment or a .env file),
  * builds a representative structured summary INCLUDING a low-confidence region,
  * calls claude-sonnet-4-6 via app.narration.narrate(),
  * prints the returned narration, and
  * asserts it (a) names the anatomy and (b) mentions the uncertainty / re-scan
    guidance — the required honest-uncertainty behavior.

Exit codes (so CI / the team can gate on it):
  0  REAL_AI narration returned and passed both assertions.
  1  ANTHROPIC_API_KEY missing or the API call fell back to the template
     (i.e. NOT in REAL_AI mode) — clear message printed.
  2  REAL_AI returned, but the text failed an assertion (names anatomy / flags
     uncertainty).

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...    # or put it in .env
    python scripts/smoke_test_narration.py
"""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

# Load .env if python-dotenv is available (so a key in .env is picked up).
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))
except Exception:
    pass

from app import narration


# A representative summary, shaped exactly like narration.build_summary() output,
# with a deliberately LOW-confidence region so we can assert the uncertainty flag.
SUMMARY = {
    "anatomy_label": "a 3D echocardiography volume (the heart's left ventricle)",
    "is_synthetic_placeholder": False,
    "approx_size": {"segmented_volume_cm3": 118.4, "bounding_box_mm": [62.1, 70.3, 58.9]},
    "pipeline_paths": {"ingestion": "PRIMARY", "preprocessing":
                       "gradient_anisotropic_diffusion(SimpleITK)",
                       "segmentation": "PRIMARY", "reconstruction": "PRIMARY",
                       "meshing": "PRIMARY", "narration": "REAL_AI"},
    "confidence": {
        "overall": 0.61, "overall_label": "medium",
        "low_confidence_regions": ["lower portion"],
        "per_region": [
            {"region": "upper portion", "confidence": 0.78, "label": "high"},
            {"region": "central portion", "confidence": 0.74, "label": "high"},
            {"region": "lower portion", "confidence": 0.42, "label": "low"},
        ],
    },
    "mesh": {"triangles": 50000, "watertight": True},
}

# Keyword sets for the two assertions (case-insensitive substring match).
ANATOMY_TERMS = ["heart", "cardi", "ventric", "echo", "chamber"]
UNCERTAINTY_TERMS = ["re-scan", "rescan", "re scan", "scan again", "uncertain",
                     "harder to capture", "lower portion", "sharper", "clearer",
                     "less clear", "confidence"]


def main() -> int:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("FAIL: ANTHROPIC_API_KEY is not set (env or .env).\n"
              "      Set it and re-run to confirm REAL_AI narration:\n"
              "        export ANTHROPIC_API_KEY=sk-ant-...", file=sys.stderr)
        return 1

    print(f"Calling {narration.NARRATION_MODEL} …")
    narr = narration.narrate(SUMMARY)
    print(f"\nmode: {narr['mode']}   model: {narr['model']}")
    print("-" * 70)
    print(narr["text"])
    print("-" * 70)

    if narr["mode"] != "REAL_AI":
        print(f"\nFAIL: narration ran in {narr['mode']} mode, not REAL_AI "
              f"({narr.get('detail')}).\n"
              "      The Claude call did not succeed — check the key/network.",
              file=sys.stderr)
        return 1

    text = narr["text"].lower()
    names_anatomy = any(t in text for t in ANATOMY_TERMS)
    flags_uncertainty = any(t in text for t in UNCERTAINTY_TERMS)

    print(f"\nassert names anatomy:      {'PASS' if names_anatomy else 'FAIL'}")
    print(f"assert flags uncertainty:  {'PASS' if flags_uncertainty else 'FAIL'}")

    if names_anatomy and flags_uncertainty:
        print("\n✅ REAL_AI narration verified — names the anatomy AND flags the "
              "low-confidence region. Ready for the judged demo.")
        return 0

    print("\nFAIL: REAL_AI returned but did not satisfy both assertions "
          "(see above). Review the system prompt in app/narration.py.",
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
