"""Stage 5 — Narration (THE AI HEADLINE).

Turns the pipeline's structured outputs into warm, plain-language AR-overlay
commentary that:
  (a) names what's visible, and
  (b) EXPLICITLY flags low-confidence regions ("this area was harder to capture
      clearly; a re-scan would give a sharper view").

The honest-uncertainty behavior is a REQUIRED feature, not a nicety — judges
should see the AI admit what it isn't sure about.

We call the Anthropic API (model `claude-sonnet-4-6`, key from the
ANTHROPIC_API_KEY env var — NEVER hardcoded). If the API key is missing or the
call fails for any reason, we fall back to a templated, non-LLM narration so
this stage NEVER crashes the demo. The status reports REAL_AI vs FALLBACK.

If the input was the synthetic placeholder phantom, that fact is passed to the
model and surfaced in the narration — a placeholder must never masquerade as a
real reconstruction.
"""

from __future__ import annotations

import json
import logging
import os

log = logging.getLogger("sonoxr.narration")

# The user-specified model for narration. Overridable via env for convenience.
NARRATION_MODEL = os.environ.get("NARRATION_MODEL", "claude-sonnet-4-6")

# System prompt: defines the warm, honest AR-overlay voice + uncertainty rule.
SYSTEM_PROMPT = (
    "You are the narration voice for an augmented-reality medical visualization. "
    "A 3D model of scanned anatomy is floating in front of the viewer. "
    "Given a JSON summary of the reconstruction, write 2-4 short sentences of warm, "
    "plain-language commentary for a non-expert. You MUST: (a) name what is visible "
    "and give a sense of its size, and (b) explicitly and honestly flag any regions "
    "the summary marks as low-confidence — say something like 'this area was harder "
    "to capture clearly, and a re-scan here would give a sharper view.' Never invent "
    "anatomical details or a diagnosis. If the summary says the data is a SYNTHETIC "
    "PLACEHOLDER, say so plainly so no one mistakes it for a real scan. Speak directly "
    "to the viewer; no preamble, no bullet points, no markdown."
)


# =============================================================================
# Build the structured summary that we feed to the model
# =============================================================================
def build_summary(*, status: dict, seg_confidence: dict, mesh_stats,
                  recon_meta: dict, anatomy_label: str,
                  is_synthetic_placeholder: bool) -> dict:
    """Assemble everything the narrator needs into one JSON-able dict.

    Includes the approximate physical size/volume (voxel count x spacing, and the
    watertight mesh volume when available), which pipeline path ran per stage,
    and the per-region confidence data from segmentation.
    """
    spacing = recon_meta.get("spacing", (1.0, 1.0, 1.0))
    voxel_count = int(recon_meta.get("voxel_count", 0))
    voxel_mm3 = float(spacing[0] * spacing[1] * spacing[2])
    seg_volume_mm3 = round(voxel_count * voxel_mm3, 1)

    summary = {
        "anatomy_label": anatomy_label,
        "is_synthetic_placeholder": is_synthetic_placeholder,
        "approx_size": {
            "segmented_volume_mm3": seg_volume_mm3,
            "segmented_volume_cm3": round(seg_volume_mm3 / 1000.0, 2),
            "mesh_volume_mm3": getattr(mesh_stats, "volume_mm3", 0.0),
            "bounding_box_mm": list(getattr(mesh_stats, "extents_mm", ())),
            "voxel_spacing_mm_zyx": [round(float(s), 3) for s in spacing],
        },
        "pipeline_paths": {
            stage: info.get("mode")
            for stage, info in status.get("stages", {}).items()
        },
        "confidence": {
            "overall": seg_confidence.get("overall"),
            "overall_label": seg_confidence.get("overall_label"),
            "low_confidence_regions": seg_confidence.get("low_confidence_regions", []),
            "per_region": seg_confidence.get("per_region", []),
        },
        "mesh": {
            "triangles": getattr(mesh_stats, "n_faces", None),
            "watertight": getattr(mesh_stats, "watertight", None),
        },
    }
    return summary


# =============================================================================
# Narrate — real LLM call with a guaranteed templated fallback
# =============================================================================
def narrate(summary: dict, timeout: float = 25.0) -> dict:
    """Return {"text", "mode", "model", "detail"}.

    mode is "REAL_AI" when the Anthropic call succeeded, else "FALLBACK".
    Never raises — any failure degrades to the templated narration.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        log.warning("ANTHROPIC_API_KEY not set — using templated narration FALLBACK.")
        return {"text": _template_narration(summary), "mode": "FALLBACK",
                "model": None,
                "detail": "ANTHROPIC_API_KEY not set; used templated narration."}

    try:
        import anthropic
    except Exception as e:
        log.warning("anthropic SDK not importable (%s) — templated FALLBACK.", e)
        return {"text": _template_narration(summary), "mode": "FALLBACK",
                "model": None, "detail": f"anthropic SDK unavailable ({e})."}

    try:
        # api_key is read from the env by default; passing it explicitly keeps the
        # contract obvious. The short timeout guarantees the demo never hangs.
        client = anthropic.Anthropic(api_key=api_key).with_options(timeout=timeout)
        user_msg = (
            "Here is the reconstruction summary as JSON. Narrate it for the viewer:\n\n"
            + json.dumps(summary, indent=2)
        )
        resp = client.messages.create(
            model=NARRATION_MODEL,
            max_tokens=400,                      # 2-4 sentences is plenty
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        # A safety refusal would leave us without usable text — fall back.
        if getattr(resp, "stop_reason", None) == "refusal":
            log.warning("Narration model refused; using templated FALLBACK.")
            return {"text": _template_narration(summary), "mode": "FALLBACK",
                    "model": NARRATION_MODEL,
                    "detail": "Model returned a safety refusal; used templated narration."}
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
        if not text:
            raise RuntimeError("empty narration text from model")
        log.info("Narration generated via %s [REAL_AI].", NARRATION_MODEL)
        return {"text": text, "mode": "REAL_AI", "model": NARRATION_MODEL,
                "detail": f"Generated by {NARRATION_MODEL}."}
    except Exception as e:
        # Covers auth errors, rate limits, network issues, bad responses — anything.
        log.warning("Narration API call failed (%s) — templated FALLBACK.", e)
        return {"text": _template_narration(summary), "mode": "FALLBACK",
                "model": NARRATION_MODEL,
                "detail": f"Anthropic call failed ({type(e).__name__}); used templated narration."}


def _template_narration(summary: dict) -> str:
    """Deterministic, dependency-free narration. Used whenever the LLM is
    unavailable. Still honest about size, low-confidence regions, and synthetic data.
    """
    label = summary.get("anatomy_label", "the scanned structure")
    vol_cm3 = summary.get("approx_size", {}).get("segmented_volume_cm3")
    low = summary.get("confidence", {}).get("low_confidence_regions", [])
    synthetic = summary.get("is_synthetic_placeholder", False)

    parts = []
    if synthetic:
        parts.append(
            "Heads up: this is a SYNTHETIC PLACEHOLDER volume, not a real scan — "
            "it's here so the pipeline can run end to end before a real scan is loaded.")
    size_str = f" It measures roughly {vol_cm3} cm³." if vol_cm3 else ""
    parts.append(f"In front of you is a 3D reconstruction of {label}.{size_str}")
    if low:
        regions = ", ".join(low)
        parts.append(
            f"The {regions} {'was' if len(low) == 1 else 'were'} harder to capture "
            "clearly — a re-scan of that area would give a sharper, more confident view.")
    else:
        parts.append("The structure came through clearly across the scanned volume.")
    return " ".join(parts)


# =============================================================================
# Echo cine narration (iteration 5) — REAL 2D echocardiogram, honest about limits
# =============================================================================
ECHO_SYSTEM_PROMPT = (
    "You narrate a REAL 2D echocardiogram (ultrasound cine of a beating heart) for "
    "a non-expert, as an AR/overlay caption. Given a JSON summary, write 2-4 warm, "
    "plain-language sentences that: (a) say this is a real beating-heart ultrasound "
    "and name what's visible (cardiac chambers in an apical view); (b) note the heart "
    "is beating and that the cardiac rhythm was captured; (c) honestly flag the "
    "regions marked low-confidence (e.g. near-field clutter at the apex, far-field "
    "dropout) as harder to see clearly. CRITICAL: do NOT state an ejection fraction, "
    "a precise chamber size, or any clinical measurement — the summary explicitly "
    "did not measure those (a trained model would be needed). Do not invent numbers "
    "or a diagnosis. Speak to the viewer; no preamble, no markdown."
)


def narrate_echo(summary: dict, timeout: float = 25.0) -> dict:
    """Honest narration for a real 2D echo cine. Returns {text, mode, model, detail}.
    LLM (claude-sonnet-4-6) when ANTHROPIC_API_KEY is set; else a templated, honest
    fallback. Never raises."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {"text": _template_echo(summary), "mode": "FALLBACK", "model": None,
                "detail": "ANTHROPIC_API_KEY not set; templated echo narration."}
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key).with_options(timeout=timeout)
        resp = client.messages.create(
            model=NARRATION_MODEL, max_tokens=400, system=ECHO_SYSTEM_PROMPT,
            messages=[{"role": "user", "content":
                       "Narrate this real 2D echo summary:\n\n" + json.dumps(summary, indent=2)}])
        if getattr(resp, "stop_reason", None) == "refusal":
            return {"text": _template_echo(summary), "mode": "FALLBACK",
                    "model": NARRATION_MODEL, "detail": "model refused; templated."}
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
        if not text:
            raise RuntimeError("empty narration")
        return {"text": text, "mode": "REAL_AI", "model": NARRATION_MODEL,
                "detail": f"Generated by {NARRATION_MODEL} (echo)."}
    except Exception as e:
        log.warning("Echo narration API failed (%s) — templated fallback.", e)
        return {"text": _template_echo(summary), "mode": "FALLBACK", "model": NARRATION_MODEL,
                "detail": f"Anthropic call failed ({type(e).__name__}); templated."}


def _template_echo(summary: dict) -> str:
    """Honest, dependency-free echo narration. States it's a real beating heart and
    the rhythm; flags low-confidence regions; explicitly does NOT claim EF/size."""
    low = summary.get("confidence", {}).get("low_confidence_regions", [])
    parts = ["This is a real 2D ultrasound of a beating heart — an apical view "
             "showing the cardiac chambers, captured live across the cardiac cycle."]
    if low:
        parts.append(f"The {', '.join(low)} {'was' if len(low) == 1 else 'were'} harder "
                     "to see clearly, which is common in echo — that region would "
                     "benefit from a better acoustic window.")
    else:
        parts.append("The chambers came through reasonably clearly across the sweep.")
    parts.append("We show the real motion and rhythm; we deliberately do not report "
                 "an ejection fraction or exact chamber size here — those need a "
                 "trained segmentation model, not raw pixel thresholds.")
    return " ".join(parts)


# =============================================================================
# CAMUS biplane LV narration (iteration 6) — real EDV/ESV/EF, honest method label
# =============================================================================
CAMUS_SYSTEM_PROMPT = (
    "You narrate a 3D left-ventricle model for a non-expert, as an AR caption. The "
    "model was reconstructed from real expert-annotated 2D apical echo views "
    "(2-chamber + 4-chamber) using Simpson's biplane method of discs — the standard "
    "clinical way to estimate LV volume. Given a JSON summary with EDV, ESV and EF, "
    "write 2-4 warm, plain-language sentences that: (a) say this is the heart's left "
    "ventricle and that it's shown beating between its fullest (end-diastole) and "
    "emptiest (end-systole); (b) state the EDV, ESV and ejection fraction in plain "
    "language and what EF means (the fraction of blood pumped out per beat); (c) be "
    "clear this is a geometric biplane reconstruction from 2D views — the clinical "
    "standard — NOT a volumetric 3D-echo acquisition. Use ONLY the numbers given; "
    "do not invent any. No diagnosis, no markdown, speak to the viewer."
)


def narrate_camus(summary: dict, timeout: float = 25.0) -> dict:
    """Honest narration for the CAMUS biplane LV. LLM when keyed, else templated."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {"text": _template_camus(summary), "mode": "FALLBACK", "model": None,
                "detail": "ANTHROPIC_API_KEY not set; templated CAMUS narration."}
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key).with_options(timeout=timeout)
        resp = client.messages.create(
            model=NARRATION_MODEL, max_tokens=400, system=CAMUS_SYSTEM_PROMPT,
            messages=[{"role": "user", "content":
                       "Narrate this LV summary:\n\n" + json.dumps(summary, indent=2)}])
        if getattr(resp, "stop_reason", None) == "refusal":
            return {"text": _template_camus(summary), "mode": "FALLBACK",
                    "model": NARRATION_MODEL, "detail": "model refused; templated."}
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
        if not text:
            raise RuntimeError("empty narration")
        return {"text": text, "mode": "REAL_AI", "model": NARRATION_MODEL,
                "detail": f"Generated by {NARRATION_MODEL} (CAMUS biplane)."}
    except Exception as e:
        log.warning("CAMUS narration API failed (%s) — templated fallback.", e)
        return {"text": _template_camus(summary), "mode": "FALLBACK", "model": NARRATION_MODEL,
                "detail": f"Anthropic call failed ({type(e).__name__}); templated."}


def _template_camus(summary: dict) -> str:
    """Honest, dependency-free CAMUS narration — states EDV/ESV/EF + the method."""
    edv = summary.get("EDV_mL"); esv = summary.get("ESV_mL"); ef = summary.get("EF_pct")
    parts = ["This is the heart's left ventricle, shown beating between its fullest "
             "point (end-diastole) and its emptiest (end-systole)."]
    if edv is not None and esv is not None and ef is not None:
        parts.append(f"It holds about {edv} mL when full and {esv} mL after the beat, "
                     f"so it pumps out roughly {ef}% each cycle — the ejection fraction.")
    parts.append("This 3D shape was reconstructed from real expert-traced 2D apical "
                 "views using Simpson's biplane method of discs — the clinical standard — "
                 "not a 3D-echo volume scan.")
    return " ".join(parts)


# =============================================================================
# MSD Task02_Heart narration (iteration 7b) — left atrium, cardiac MRI, honest
# =============================================================================
MSD_SYSTEM_PROMPT = (
    "You narrate a 3D left-atrium model for a non-expert, as an AR caption. The "
    "model was reconstructed from an expert MRI segmentation mask (MSD Task02_Heart, "
    "label 1 = left atrium) using marching cubes on the real 3D voxel volume — NOT "
    "ultrasound, NOT Simpson's biplane. Given a JSON summary, write 2-4 warm, "
    "plain-language sentences that: (a) name this as the left atrium — the upper-left "
    "chamber of the heart that receives oxygenated blood from the lungs; (b) note this "
    "is a true 3D cardiac MRI volume, not ultrasound; (c) state its approximate volume "
    "in cm³ and physical extent; (d) be clear this was built from expert segmentation "
    "labels, not raw image intensity. Do NOT state an EF — this dataset has none. "
    "No diagnosis, no markdown, speak to the viewer."
)


def narrate_msd(summary: dict, timeout: float = 25.0) -> dict:
    """Honest narration for the MSD Task02_Heart left atrium. LLM when keyed, else templated."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {"text": _template_msd(summary), "mode": "FALLBACK", "model": None,
                "detail": "ANTHROPIC_API_KEY not set; templated MSD narration."}
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key).with_options(timeout=timeout)
        resp = client.messages.create(
            model=NARRATION_MODEL, max_tokens=400, system=MSD_SYSTEM_PROMPT,
            messages=[{"role": "user", "content":
                       "Narrate this left-atrium summary:\n\n" + json.dumps(summary, indent=2)}])
        if getattr(resp, "stop_reason", None) == "refusal":
            return {"text": _template_msd(summary), "mode": "FALLBACK",
                    "model": NARRATION_MODEL, "detail": "model refused; templated."}
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
        if not text:
            raise RuntimeError("empty narration")
        return {"text": text, "mode": "REAL_AI", "model": NARRATION_MODEL,
                "detail": f"Generated by {NARRATION_MODEL} (MSD left atrium)."}
    except Exception as e:
        log.warning("MSD narration API failed (%s) — templated fallback.", e)
        return {"text": _template_msd(summary), "mode": "FALLBACK", "model": NARRATION_MODEL,
                "detail": f"Anthropic call failed ({type(e).__name__}); templated."}


def _template_msd(summary: dict) -> str:
    """Honest, dependency-free MSD narration — left atrium, MRI, no EF."""
    vol  = summary.get("mesh_volume_cm3")
    ext  = summary.get("extents_mm")
    ext_str = (f" It spans roughly {ext[0]:.0f}×{ext[1]:.0f}×{ext[2]:.0f} mm."
               if ext and len(ext) == 3 else "")
    vol_str = f" Its reconstructed volume is about {vol} cm³." if vol else ""
    parts = [
        "This is the left atrium — the upper-left chamber of the heart that collects "
        "oxygenated blood returning from the lungs before it flows into the left ventricle.",
        f"This is a true 3D shape from a real cardiac MRI scan (not ultrasound).{vol_str}{ext_str}",
        "The mesh was built from expert segmentation labels using marching cubes on "
        "the real MRI voxel volume — the geometry is the actual annotated anatomy, "
        "not a raw-intensity estimate.",
    ]
    return " ".join(parts)
