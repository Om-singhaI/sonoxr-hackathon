import { type CSSProperties } from 'react'
import { Link } from 'react-router-dom'
import { PATIENTS, toneColor } from '../data/patients'
import { FONT_DISPLAY, FONT_BODY, FONT_MONO, C } from '../theme'

const sectionNum: CSSProperties = {
  fontFamily: FONT_MONO,
  fontSize: 12,
  letterSpacing: '.16em',
  color: C.redSoft,
  textTransform: 'uppercase',
  margin: '0 0 16px',
}
const h2: CSSProperties = {
  fontFamily: FONT_DISPLAY,
  fontWeight: 600,
  fontSize: 26,
  letterSpacing: '-0.02em',
  color: C.textPrimary,
  marginBottom: 14,
}
const para: CSSProperties = {
  fontSize: 16,
  lineHeight: 1.62,
  color: C.textBody2,
  marginBottom: 16,
}
const chip: CSSProperties = {
  fontFamily: FONT_MONO,
  fontSize: 11,
  letterSpacing: '.06em',
  color: '#C7CDD6',
  padding: '7px 13px',
  border: '1px solid rgba(255,255,255,.12)',
  borderRadius: 999,
  background: 'rgba(255,255,255,.03)',
}

export default function Writeup() {
  const pipeline = [
    { n: '01', t: 'Capture', d: 'Biplane apical views + expert contours.' },
    { n: '02', t: 'Reconstruct', d: 'Temporally-consistent LV mesh + per-vertex confidence.' },
    { n: '03', t: 'Inhabit', d: 'Grab it in MR; ask the agent grounded questions.' },
  ]
  return (
    <section
      style={{
        position: 'relative',
        width: '100%',
        minHeight: '100vh',
        background: 'radial-gradient(120% 60% at 50% -8%, #11141B 0%, #0A0C11 50%, #07090B 100%)',
        color: '#EEF1F5',
        paddingBottom: 80,
        fontFamily: FONT_BODY,
      }}
    >
      <header
        style={{
          position: 'sticky',
          top: 0,
          zIndex: 20,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '18px 40px',
          background: 'rgba(7,9,11,.78)',
          backdropFilter: 'blur(10px)',
          borderBottom: '1px solid rgba(255,255,255,.07)',
        }}
      >
        <Link
          to="/login"
          style={{ display: 'flex', alignItems: 'center', gap: 12, textDecoration: 'none', color: 'inherit' }}
        >
          <div
            style={{
              width: 12,
              height: 12,
              borderRadius: '50%',
              background: C.red,
              boxShadow: '0 0 14px 2px rgba(225,29,51,.6)',
              animation: 'sonoPulse 1s ease-in-out infinite',
            }}
          />
          <span style={{ fontFamily: FONT_DISPLAY, fontWeight: 700, fontSize: 17 }}>SonoXR</span>
        </Link>
        <div style={{ display: 'flex', gap: 18, alignItems: 'center' }}>
          <Link
            to="/login"
            style={{
              fontFamily: FONT_MONO,
              fontSize: 11,
              letterSpacing: '.12em',
              color: C.textMuted,
              textTransform: 'uppercase',
              textDecoration: 'none',
            }}
          >
            Web demo
          </Link>
          <Link
            to="/login"
            style={{
              fontFamily: FONT_MONO,
              fontSize: 11,
              letterSpacing: '.12em',
              color: C.blueText,
              textTransform: 'uppercase',
              textDecoration: 'none',
            }}
          >
            Sign up →
          </Link>
        </div>
      </header>

      <article style={{ maxWidth: 720, margin: '0 auto', padding: '60px 28px 0' }}>
        <div
          style={{
            fontFamily: FONT_MONO,
            fontSize: 11.5,
            letterSpacing: '.22em',
            color: C.blue,
            textTransform: 'uppercase',
            marginBottom: 18,
          }}
        >
          Technical write-up · v0.1
        </div>
        <h1
          style={{
            fontFamily: FONT_DISPLAY,
            fontWeight: 700,
            fontSize: 'clamp(32px,4.4vw,52px)',
            lineHeight: 1.05,
            letterSpacing: '-0.025em',
            color: C.textPrimary,
            marginBottom: 20,
            textWrap: 'balance' as CSSProperties['textWrap'],
          }}
        >
          Reconstructing a beating left ventricle from 2D echo — and being honest about it.
        </h1>
        <p style={{ fontSize: 17, lineHeight: 1.62, color: C.textBody, marginBottom: 14 }}>
          SonoXR turns an ordinary 2D cardiac ultrasound into a temporally-consistent 3D model of
          the left ventricle that a clinician can hold in mixed reality on a Meta Quest 3. The
          defining feature is not the reconstruction itself but the{' '}
          <span style={{ color: C.textPrimary }}>calibrated honesty layer</span>: every region of
          the mesh carries the model's own confidence, and the agent refuses to narrate past what
          the echo supports.
        </p>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', margin: '26px 0 40px' }}>
          <span style={chip}>CAMUS dataset</span>
          <span style={chip}>Quest 3 · WebXR</span>
          <span style={chip}>Grounded narration</span>
          <span style={chip}>Deepgram voice</span>
        </div>

        <div style={sectionNum}>01 · The pipeline</div>
        <h2 style={h2}>From a 2D sweep to a 3D ventricle</h2>
        <p style={para}>
          We start from apical 4-chamber and 2-chamber views with expert LV masks. End-diastolic
          and end-systolic contours are lifted into a biplane geometry, then fitted to a
          temporally-consistent mesh so the chamber deforms as one organ across the cardiac cycle
          rather than flickering frame to frame. Volumes (EDV, ESV) and ejection fraction follow
          directly from the reconstructed cavity.
        </p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 12, margin: '24px 0 40px' }}>
          {pipeline.map((s) => (
            <div
              key={s.n}
              style={{
                border: '1px solid rgba(255,255,255,.09)',
                borderRadius: 13,
                background: 'rgba(9,13,20,.5)',
                padding: 18,
              }}
            >
              <div style={{ fontFamily: FONT_MONO, fontSize: 12, color: C.redSoft, marginBottom: 8 }}>
                {s.n}
              </div>
              <div
                style={{
                  fontFamily: FONT_DISPLAY,
                  fontWeight: 600,
                  fontSize: 16,
                  color: C.textPrimary,
                  marginBottom: 4,
                }}
              >
                {s.t}
              </div>
              <div style={{ fontSize: 13.5, lineHeight: 1.5, color: C.textMuted2 }}>{s.d}</div>
            </div>
          ))}
        </div>

        <div style={sectionNum}>02 · The honesty layer</div>
        <h2 style={h2}>Confidence carried end to end</h2>
        <p style={para}>
          Each vertex keeps a confidence value from reconstruction through to narration. Basal
          segments near the mitral annulus — which move most between frames — are systematically
          less certain, and the model says so rather than smoothing it over. The heatmap you see on
          the heart is the model's own doubt, not a cosmetic overlay. When acoustic windows are
          poor, confidence drops globally and the agent widens its uncertainty instead of
          over-committing to a crisp number.
        </p>
        <blockquote
          style={{
            borderLeft: '2px solid rgba(245,167,66,.5)',
            background: 'rgba(245,167,66,.05)',
            padding: '16px 20px',
            borderRadius: '0 11px 11px 0',
            margin: '22px 0 40px',
          }}
        >
          <div style={{ fontSize: 15.5, lineHeight: 1.6, color: '#E4E8EE', fontStyle: 'italic' }}>
            "Least certain: apical septal wall — low echo contrast in this view."
          </div>
          <div
            style={{
              fontFamily: FONT_MONO,
              fontSize: 11,
              letterSpacing: '.1em',
              color: C.textMuted,
              textTransform: 'uppercase',
              marginTop: 8,
            }}
          >
            — the model, flagging its own weak spot
          </div>
        </blockquote>

        <div style={sectionNum}>03 · The data</div>
        <h2 style={h2}>Five real CAMUS studies</h2>
        <p style={{ ...para, marginBottom: 18 }}>
          The demo ships with five reconstructed patients spanning the clinical range — from normal
          function to severely reduced, and one deliberately poor-quality study to show the honesty
          layer earning its keep.
        </p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 40 }}>
          {PATIENTS.map((p) => (
            <div
              key={p.id}
              style={{
                display: 'grid',
                gridTemplateColumns: '120px 64px 1fr',
                gap: 14,
                alignItems: 'center',
                border: '1px solid rgba(255,255,255,.08)',
                borderRadius: 11,
                background: 'rgba(9,13,20,.45)',
                padding: '13px 16px',
              }}
            >
              <span style={{ fontFamily: FONT_DISPLAY, fontWeight: 600, fontSize: 14, color: C.textPrimary }}>
                {p.label}
              </span>
              <span style={{ fontFamily: FONT_DISPLAY, fontWeight: 700, fontSize: 16, color: toneColor(p.tone) }}>
                {p.ef}%
              </span>
              <span style={{ fontSize: 13, color: C.textMuted2 }}>
                {p.category} · {p.quality} image quality
              </span>
            </div>
          ))}
        </div>

        <div style={sectionNum}>04 · In the headset</div>
        <h2 style={h2}>Web view and VR view, one console</h2>
        <p style={para}>
          The reconstruction runs on-device on Quest 3 — a patient's scan never has to leave for the
          cloud to be viewed. The web console mirrors the in-headset dashboard: ultrasound scans on
          the left, the reconstructed heart in the centre, and the AI analysis — ejection fraction,
          flagged uncertainty, and grounded answers spoken aloud via Deepgram — on the right. The
          same study opens in either place.
        </p>

        <div
          style={{
            display: 'flex',
            gap: 14,
            flexWrap: 'wrap',
            marginTop: 44,
            paddingTop: 34,
            borderTop: '1px solid rgba(255,255,255,.08)',
          }}
        >
          <Link
            to="/login"
            className="app-redbtn"
            style={{
              padding: '14px 26px',
              borderRadius: 10,
              background: C.red,
              color: '#fff',
              fontWeight: 600,
              fontSize: 15,
              textDecoration: 'none',
              boxShadow: '0 8px 26px -8px rgba(225,29,51,.6)',
            }}
          >
            Open the web demo
          </Link>
          <Link
            to="/login"
            className="app-ghostbtn"
            style={{
              padding: '14px 26px',
              borderRadius: 10,
              border: '1px solid rgba(255,255,255,.14)',
              background: 'rgba(255,255,255,.03)',
              color: '#E4E8EE',
              fontWeight: 600,
              fontSize: 15,
              textDecoration: 'none',
            }}
          >
            Sign up
          </Link>
        </div>
        <div style={{ fontSize: 11.5, lineHeight: 1.5, color: C.textDim2, textAlign: 'center', marginTop: 40 }}>
          SonoXR is a research prototype · Not a medical device · Not for clinical use
        </div>
      </article>
    </section>
  )
}
