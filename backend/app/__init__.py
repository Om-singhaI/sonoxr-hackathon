"""SonoXR / EchoAR backend package.

A FastAPI service that turns a volumetric ultrasound (3D/4D DICOM) into a
mobile-AR-ready .glb mesh plus plain-language, uncertainty-aware narration.

See app/pipeline.py for the orchestration and the PRIMARY-vs-FALLBACK logic,
and README.md for the per-stage "REAL AI vs FALLBACK" breakdown.
"""

__version__ = "0.1.0"
