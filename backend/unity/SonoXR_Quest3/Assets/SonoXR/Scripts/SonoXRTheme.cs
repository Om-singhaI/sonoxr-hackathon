// SonoXRTheme.cs
// Central visual theme — colors, rounded-corner sprite factory, shared UI helpers.
// All Image components call ApplyCard() instead of setting .color directly.

using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;
using TMPro;

public static class SonoXRTheme
{
    // ── Backgrounds ───────────────────────────────────────────────────────────────
    public static readonly Color BG_DEEP   = new Color(0.02f, 0.03f, 0.09f, 0.97f);
    public static readonly Color BG_PANEL  = new Color(0.04f, 0.07f, 0.17f, 0.94f);
    public static readonly Color BG_CARD   = new Color(0.06f, 0.11f, 0.23f, 0.92f);
    public static readonly Color BG_INSET  = new Color(0.02f, 0.04f, 0.11f, 0.88f);

    // ── Buttons ───────────────────────────────────────────────────────────────────
    public static readonly Color BTN_NRM   = new Color(0.08f, 0.14f, 0.28f, 1.00f);
    public static readonly Color BTN_HOV   = new Color(0.14f, 0.28f, 0.50f, 1.00f);
    public static readonly Color BTN_PRE   = new Color(0.08f, 0.52f, 0.74f, 1.00f);
    public static readonly Color BTN_REC   = new Color(0.65f, 0.07f, 0.07f, 1.00f);

    // ── Accents ───────────────────────────────────────────────────────────────────
    public static readonly Color CYAN      = new Color(0.18f, 0.80f, 0.95f, 1.00f);
    public static readonly Color CYAN_DIM  = new Color(0.10f, 0.40f, 0.58f, 1.00f);
    public static readonly Color CYAN_LINE = new Color(0.18f, 0.80f, 0.95f, 0.30f);
    public static readonly Color INDIGO    = new Color(0.45f, 0.35f, 0.92f, 1.00f);

    // ── Text ─────────────────────────────────────────────────────────────────────
    public static readonly Color TXT_WHITE = new Color(0.94f, 0.97f, 1.00f, 1.00f);
    public static readonly Color TXT_BLUE  = new Color(0.72f, 0.88f, 0.98f, 1.00f);
    public static readonly Color TXT_MUTED = new Color(0.48f, 0.62f, 0.78f, 1.00f);
    public static readonly Color TXT_HINT  = new Color(0.32f, 0.42f, 0.58f, 1.00f);

    // ── EF indicators ─────────────────────────────────────────────────────────────
    public static readonly Color EF_GREEN  = new Color(0.22f, 0.86f, 0.58f, 1.00f);
    public static readonly Color EF_AMBER  = new Color(1.00f, 0.72f, 0.15f, 1.00f);
    public static readonly Color EF_RED    = new Color(1.00f, 0.28f, 0.28f, 1.00f);

    // ── Misc ─────────────────────────────────────────────────────────────────────
    public static readonly Color WARNING   = new Color(1.00f, 0.80f, 0.25f, 1.00f);

    // ── Rounded sprite cache ──────────────────────────────────────────────────────

    static readonly Dictionary<int, Sprite> _cache = new();

    /// <summary>
    /// Returns a white 9-slice rounded-corner sprite.
    /// Apply to Image + set Image.type = Sliced, then tint via Image.color.
    /// </summary>
    public static Sprite CardSprite(int radius = 16)
    {
        if (_cache.TryGetValue(radius, out var hit) && hit != null) return hit;

        int size = radius * 2 + 4;
        var tex  = new Texture2D(size, size, TextureFormat.RGBA32, false);
        tex.filterMode = FilterMode.Bilinear;
        tex.wrapMode   = TextureWrapMode.Clamp;

        for (int y = 0; y < size; y++)
        for (int x = 0; x < size; x++)
        {
            float px = Mathf.Clamp(x, radius, size - 1 - radius);
            float py = Mathf.Clamp(y, radius, size - 1 - radius);
            float d  = Mathf.Sqrt((x - px) * (x - px) + (y - py) * (y - py));
            float a  = Mathf.Clamp01(radius + 0.5f - d);
            tex.SetPixel(x, y, new Color(1f, 1f, 1f, a));
        }
        tex.Apply();

        float r = radius;
        var sp = Sprite.Create(tex,
            new Rect(0, 0, size, size),
            new Vector2(0.5f, 0.5f),
            100f, 0, SpriteMeshType.FullRect,
            new Vector4(r, r, r, r));

        return _cache[radius] = sp;
    }

    /// <summary>Applies a rounded-corner card sprite to an Image.</summary>
    public static void ApplyCard(Image img, Color color, int radius = 16)
    {
        img.sprite = CardSprite(radius);
        img.type   = Image.Type.Sliced;
        img.color  = color;
    }

    /// <summary>Shared button ColorBlock — all buttons in the app use this.</summary>
    public static ColorBlock BtnColors() => new ColorBlock
    {
        normalColor      = BTN_NRM,
        highlightedColor = BTN_HOV,
        pressedColor     = BTN_PRE,
        selectedColor    = BTN_HOV,
        disabledColor    = new Color(0.22f, 0.22f, 0.22f),
        colorMultiplier  = 1f,
        fadeDuration     = 0.12f
    };

    /// <summary>Creates a thin horizontal accent line — use as section divider.</summary>
    public static void AddDivider(Transform parent, float height = 2f, Color? color = null)
    {
        var go  = new GameObject("Divider");
        go.transform.SetParent(parent, false);
        var img = go.AddComponent<Image>();
        img.color = color ?? CYAN_LINE;
        var le  = go.AddComponent<LayoutElement>();
        le.preferredHeight = height;
    }

    /// <summary>Creates a section label — small all-caps styled TMP text.</summary>
    public static TextMeshProUGUI AddSectionLabel(Transform parent, string text, float height = 28f)
    {
        var go  = new GameObject("SectionLabel");
        go.transform.SetParent(parent, false);
        var tmp = go.AddComponent<TextMeshProUGUI>();
        tmp.text             = text.ToUpperInvariant();
        tmp.fontSize         = 14f;
        tmp.fontStyle        = FontStyles.Bold;
        tmp.color            = TXT_MUTED;
        tmp.alignment        = TextAlignmentOptions.MidlineLeft;
        tmp.characterSpacing = 3f;
        var le = go.AddComponent<LayoutElement>();
        le.preferredHeight = height;
        return tmp;
    }
}
