// SonoXRShaders.cs
// Material helpers for Quest 3 MR.
//
// PANEL RULE: always use Sprites/Default for 2D world-space quads.
//   - Guaranteed in every Unity Android build (UI system requires it).
//   - Unlit — no lighting needed for AR overlays.
//   - Two-sided by default — no _Cull override needed.
//   - Works identically in Built-in RP and URP.
//   - Supports both solid colour (mat.color) and texture (mat.mainTexture).
//
// 3D MESH RULE: use Universal Render Pipeline/Lit (or Standard fallback)
//   for the heart — needs lighting/emission. The heart already renders
//   correctly; do not change MakeCrimson.

using UnityEngine;
using UnityEngine.Rendering;

public static class SonoXRShaders
{
    // ── shader selection ──────────────────────────────────────────────────────────

    // Sprites/Default: unlit, two-sided, texture+colour, always in build.
    static Shader PanelShader()
    {
        var sh = Shader.Find("Sprites/Default");
        if (sh != null) return sh;
        Debug.LogError("[SonoXRShaders] Sprites/Default not found — check Always Included Shaders.");
        return Shader.Find("Unlit/Color") ?? Shader.Find("Unlit/Texture");
    }

    // Unlit/Color: for LineRenderers and solid primitives that need no texture.
    static Shader LineShader()
        => Shader.Find("Unlit/Color") ?? Shader.Find("Sprites/Default");

    // URP/Lit (or Standard fallback) for 3D mesh emission.
    static Shader MeshShader()
        => Shader.Find("Universal Render Pipeline/Lit")
        ?? Shader.Find("Standard")
        ?? Shader.Find("Diffuse");

    // ── panel material factories ──────────────────────────────────────────────────

    // Solid-colour panel background — alpha forced to 1.
    public static Material MakeOpaque(Color color)
    {
        var mat = new Material(PanelShader());
        mat.color = new Color(color.r, color.g, color.b, 1f);
        return mat;
    }

    // Semi-transparent panel — alpha taken from the color argument.
    // Use for backdrop quads and hover overlays. Relies on Sprites/Default premult blending.
    public static Material MakeTranslucent(Color color)
    {
        var mat = new Material(PanelShader());
        mat.color = color;
        return mat;
    }

    // Solid colour for LineRenderers, cursor dots, and simple unlit primitives.
    public static Material MakeLine(Color color)
    {
        var mat = new Material(LineShader());
        mat.color = new Color(color.r, color.g, color.b, 1f);
        return mat;
    }

    // Ultrasound image panel — texture displayed without lighting.
    public static Material MakeUnlitTexture(Texture2D tex)
    {
        if (tex == null)
        {
            Debug.LogWarning("[SonoXRShaders] MakeUnlitTexture: tex is null — returning placeholder");
            return MakeOpaque(new Color(0.12f, 0.14f, 0.20f));
        }
        var mat = new Material(PanelShader());
        mat.mainTexture = tex;
        mat.color       = Color.white;
        Debug.Log($"[SonoXRShaders] Panel texture applied: {tex.width}×{tex.height}");
        return mat;
    }

    // ── 3D mesh material factories ────────────────────────────────────────────────

    // Emissive crimson — reconstructed LV mesh. Do NOT use for panels.
    public static Material MakeCrimson(Color baseColor, Color emitColor)
    {
        var mat = new Material(MeshShader());
        mat.SetColor("_BaseColor", baseColor);
        mat.SetColor("_Color",     baseColor);
        mat.SetColor("_EmissionColor", emitColor);
        mat.EnableKeyword("_EMISSION");
        mat.globalIlluminationFlags = MaterialGlobalIlluminationFlags.RealtimeEmissive;
        mat.SetFloat("_Glossiness", 0.40f);
        mat.SetFloat("_Smoothness", 0.40f);
        mat.SetFloat("_Metallic",   0.05f);
        mat.SetInt("_Cull", (int)CullMode.Off);
        return mat;
    }

    // Transparent shell — kept for API compat; shell is currently disabled in HeartVisuals.
    public static Material MakeTransparent(Color color)
    {
        var mat = new Material(PanelShader());
        mat.color = color;
        return mat;
    }
}
