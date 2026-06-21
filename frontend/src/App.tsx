import { useEffect, useState, type CSSProperties } from 'react'
import { Link } from 'react-router-dom'
import HeartScene from './HeartScene'

// true on phone-width viewports — drives the responsive layout below
function useIsMobile(query = '(max-width: 768px)') {
  const [m, setM] = useState(
    () => typeof window !== 'undefined' && window.matchMedia(query).matches,
  )
  useEffect(() => {
    const mq = window.matchMedia(query)
    const on = () => setM(mq.matches)
    on()
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [query])
  return m
}

/*
 * SonoXR — scroll-cinematic landing page.
 *
 * The 8 transparent content sections scroll over a single fixed WebGL canvas
 * (<HeartScene/>, z-index 1). Copy is final/verbatim per the design handoff.
 *
 * TODO(client): the three "money" CTAs below are dead-end placeholders awaiting
 * real destinations. They are wired to in-page anchors for now and marked with
 * `data-todo`. Drop in a real route / form / video when available:
 *   - "Watch the Quest 3 demo"  → real demo (video or /demo viewer)   [#demo]
 *   - "Request access" (top bar) / "Request a pilot" (access section) → Request Access form/route
 *   - "Read the technical write-up" → docs / write-up page            [#tech]
 */

const FONT_DISPLAY = "'Space Grotesk', sans-serif"
const FONT_BODY = "'Archivo', sans-serif"
const FONT_MONO = "'IBM Plex Mono', monospace"

const mono = (extra: CSSProperties = {}): CSSProperties => ({
  fontFamily: FONT_MONO,
  textTransform: 'uppercase',
  ...extra,
})

const revealStyle: CSSProperties = {
  opacity: 0,
  transform: 'translateY(26px)',
  transition:
    'opacity .85s cubic-bezier(.2,.7,.2,1), transform .85s cubic-bezier(.2,.7,.2,1)',
}

const cardGlassLarge: CSSProperties = {
  background: 'rgba(9,11,15,.55)',
  backdropFilter: 'blur(10px)',
  WebkitBackdropFilter: 'blur(10px)',
  border: '1px solid rgba(255,255,255,.08)',
  borderRadius: 18,
  padding: '38px 40px',
}

// Glass list cards (3× How, 3× Clinical). The reference shows the heart softly
// blurred through these, so we keep a real backdrop blur. A slightly more opaque
// base than the prototype trims the per-frame re-blur cost a little.
const cardGlassSmall: CSSProperties = {
  background: 'rgba(9,11,15,.58)',
  backdropFilter: 'blur(9px)',
  WebkitBackdropFilter: 'blur(9px)',
  border: '1px solid rgba(255,255,255,.08)',
  borderRadius: 14,
  padding: '20px 22px',
}

const sectionBase: CSSProperties = {
  position: 'relative',
  zIndex: 10,
  minHeight: '100vh',
  fontFamily: FONT_BODY,
  color: '#EEF1F5',
}

const h2Style: CSSProperties = {
  fontFamily: FONT_DISPLAY,
  fontWeight: 700,
  fontSize: 'clamp(30px,3vw,46px)',
  lineHeight: 1.05,
  letterSpacing: '-0.025em',
  color: '#F4F6F9',
  textWrap: 'balance' as CSSProperties['textWrap'],
}

const eyebrow = (color = '#9AA3B0'): CSSProperties =>
  mono({
    fontSize: 11.5,
    letterSpacing: '.22em',
    color,
    marginBottom: 18,
  })

const NAV = [
  { id: 'hero', title: 'Intro' },
  { id: 'honesty', title: 'Honesty layer' },
  { id: 'how', title: 'How it works' },
  { id: 'demo', title: 'Demo' },
  { id: 'tech', title: 'Under the hood' },
  { id: 'clinical', title: "Who it's for" },
  { id: 'team', title: 'Team' },
  { id: 'access', title: 'Access' },
]

export default function App() {
  const isMobile = useIsMobile()

  // reveal-on-scroll: [data-reveal] fades/slides in via IntersectionObserver
  useEffect(() => {
    const els = Array.from(document.querySelectorAll<HTMLElement>('[data-reveal]'))
    const reduce =
      window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (reduce) {
      els.forEach((e) => {
        e.style.opacity = '1'
        e.style.transform = 'none'
      })
      return
    }
    const io = new IntersectionObserver(
      (ents) => {
        ents.forEach((en) => {
          if (en.isIntersecting) {
            const el = en.target as HTMLElement
            el.style.opacity = '1'
            el.style.transform = 'none'
            io.unobserve(el)
          }
        })
      },
      { threshold: 0.15, rootMargin: '0px 0px -8% 0px' },
    )
    els.forEach((e) => io.observe(e))
    // safety: never leave content invisible if the observer misses
    const safety = window.setTimeout(() => {
      els.forEach((e) => {
        if (getComputedStyle(e).opacity === '0') {
          e.style.opacity = '1'
          e.style.transform = 'none'
        }
      })
    }, 4000)
    return () => {
      io.disconnect()
      window.clearTimeout(safety)
    }
  }, [])

  return (
    <>
      {/* ===== FIXED BACKDROP LAYERS ===== */}
      <div
        style={{
          position: 'fixed',
          inset: 0,
          zIndex: 0,
          pointerEvents: 'none',
          background:
            'radial-gradient(120% 90% at 50% 8%, #11141B 0%, #0A0C11 38%, #07090B 100%)',
        }}
      />
      <div
        id="sono-ambient-r"
        style={{
          position: 'fixed',
          inset: 0,
          zIndex: 0,
          pointerEvents: 'none',
          background:
            'radial-gradient(70% 65% at 50% 46%, rgba(225,29,51,0.18) 0%, rgba(225,29,51,0.10) 22%, rgba(225,29,51,0.04) 46%, rgba(225,29,51,0.012) 70%, rgba(225,29,51,0) 88%)',
          transition: 'opacity .6s ease',
        }}
      />
      <div
        style={{
          position: 'fixed',
          inset: 0,
          zIndex: 0,
          pointerEvents: 'none',
          background:
            'radial-gradient(55% 50% at 66% 34%, rgba(79,168,255,0.08) 0%, rgba(79,168,255,0.02) 42%, rgba(79,168,255,0) 78%)',
        }}
      />

      {/* ===== WEBGL HEART (fixed, z-index 1) ===== */}
      <HeartScene />

      {/* vignette over the canvas */}
      <div
        style={{
          position: 'fixed',
          inset: 0,
          zIndex: 2,
          pointerEvents: 'none',
          background:
            'radial-gradient(135% 95% at 50% 42%, rgba(7,9,11,0) 52%, rgba(7,9,11,0.42) 80%, rgba(7,9,11,0.82) 100%)',
        }}
      />

      {/* ===== FIXED TOP BAR ===== */}
      <header
        style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          zIndex: 50,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: isMobile ? '15px 18px' : '22px 40px',
          fontFamily: FONT_BODY,
          animation: 'sonoFade .9s ease both',
          background: 'linear-gradient(180deg, rgba(7,9,11,0.55) 0%, rgba(7,9,11,0) 100%)',
        }}
      >
        <a
          href="#hero"
          style={{ display: 'flex', alignItems: 'center', gap: 11, textDecoration: 'none' }}
        >
          <div
            style={{
              width: 13,
              height: 13,
              borderRadius: '50%',
              background: '#E11D33',
              boxShadow: '0 0 16px 3px rgba(225,29,51,.65)',
              animation: 'sonoPulse 1s ease-in-out infinite',
            }}
          />
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 9 }}>
            <span
              style={{
                fontFamily: FONT_DISPLAY,
                fontWeight: 700,
                fontSize: 19,
                letterSpacing: '.02em',
                color: '#EEF1F5',
              }}
            >
              SonoXR
            </span>
            <span style={mono({ fontSize: 11, letterSpacing: '.16em', color: '#7C8694' })}>
              EchoAR
            </span>
          </div>
        </a>
        <div style={{ display: 'flex', alignItems: 'center', gap: isMobile ? 14 : 22 }}>
          {!isMobile && (
            <Link
              to="/dashboard"
              style={{
                ...mono({ fontSize: 11, letterSpacing: '.14em', color: '#9CCBFF' }),
                textDecoration: 'none',
              }}
            >
              Launch dashboard
            </Link>
          )}
          <Link
            to="/login"
            className="sono-pill"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              padding: '8px 16px',
              border: '1px solid rgba(255,255,255,.14)',
              borderRadius: 999,
              background: 'rgba(255,255,255,.03)',
              textDecoration: 'none',
            }}
          >
            <span
              style={{
                width: 6,
                height: 6,
                borderRadius: '50%',
                background: '#4FA8FF',
                boxShadow: '0 0 10px 2px rgba(79,168,255,.6)',
              }}
            />
            <span style={mono({ fontSize: 11, letterSpacing: '.12em', color: '#C7CDD6' })}>
              Log in / Sign up
            </span>
          </Link>
        </div>
      </header>

      {/* ===== SECTION NAV DOTS ===== */}
      <nav
        style={{
          position: 'fixed',
          right: 26,
          top: '50%',
          transform: 'translateY(-50%)',
          zIndex: 50,
          display: isMobile ? 'none' : 'flex',
          flexDirection: 'column',
          gap: 14,
        }}
      >
        {NAV.map((nav, i) => (
          <a
            key={nav.id}
            href={`#${nav.id}`}
            data-navdot={i}
            title={nav.title}
            style={{
              width: 9,
              height: 9,
              borderRadius: '50%',
              background: 'rgba(255,255,255,.22)',
              transition: 'background .25s, transform .25s, box-shadow .25s',
            }}
          />
        ))}
      </nav>

      {/* ===== 1. HERO ===== */}
      <section
        id="hero"
        style={{
          ...sectionBase,
          display: 'flex',
          alignItems: 'flex-end',
          padding: isMobile ? '0 20px 32px' : '0 40px 42px',
        }}
      >
        <div
          style={{
            width: '100%',
            display: 'flex',
            alignItems: 'flex-end',
            justifyContent: 'space-between',
            gap: 40,
          }}
        >
          <div style={{ maxWidth: 760, width: isMobile ? '100%' : undefined }}>
            <div
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 12,
                marginBottom: 22,
                animation: 'sonoUp .8s ease both',
              }}
            >
              <span style={mono({ fontSize: 11.5, letterSpacing: '.22em', color: '#9AA3B0' })}>
                Cardiac reconstruction
              </span>
              <span style={{ width: 4, height: 4, borderRadius: '50%', background: '#E11D33' }} />
              <span style={mono({ fontSize: 11.5, letterSpacing: '.22em', color: '#E1485C' })}>
                Mixed reality
              </span>
            </div>
            <h1
              style={{
                fontFamily: FONT_DISPLAY,
                fontWeight: 700,
                fontSize: 'clamp(38px,4.6vw,72px)',
                lineHeight: 1.02,
                letterSpacing: '-0.025em',
                color: '#F4F6F9',
                textWrap: 'balance' as CSSProperties['textWrap'],
                marginBottom: 20,
                animation: 'sonoUp .8s ease .08s both',
              }}
            >
              Hold a patient's beating heart,
              <br />
              reconstructed from a <span style={{ color: '#E11D33' }}>2D&nbsp;ultrasound</span>.
            </h1>
            <p
              style={{
                fontSize: 'clamp(15px,1.25vw,18.5px)',
                lineHeight: 1.55,
                color: '#A6AEBA',
                maxWidth: 610,
                marginBottom: 30,
                animation: 'sonoUp .8s ease .16s both',
              }}
            >
              SonoXR rebuilds the left ventricle from ordinary cardiac echo into a living 3D model
              you can grab in mixed reality — calibrated to tell you exactly what it can't see.
            </p>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 18,
                flexWrap: 'wrap',
                animation: 'sonoUp .8s ease .24s both',
              }}
            >
              <a
                href="#honesty"
                className="sono-btn-primary"
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 10,
                  padding: '15px 26px',
                  borderRadius: 10,
                  background: '#E11D33',
                  color: '#fff',
                  fontWeight: 600,
                  fontSize: 15,
                  textDecoration: 'none',
                  boxShadow: '0 8px 30px -6px rgba(225,29,51,.55)',
                }}
              >
                See the honesty layer
                <span style={{ fontFamily: FONT_MONO, fontSize: 16, lineHeight: 1 }}>→</span>
              </a>
              {/* Watch demo → the web demo (login gate) per the app link graph */}
              <Link
                to="/login"
                className="sono-chip"
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 13,
                  padding: '9px 16px 9px 9px',
                  borderRadius: 12,
                  border: '1px solid rgba(255,255,255,.12)',
                  background: 'rgba(255,255,255,.035)',
                  textDecoration: 'none',
                }}
              >
                <span
                  style={{
                    position: 'relative',
                    width: 74,
                    height: 46,
                    borderRadius: 7,
                    overflow: 'hidden',
                    flex: 'none',
                    background:
                      'repeating-linear-gradient(135deg,#15181F 0 8px,#1B1F28 8px 16px)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                >
                  <span
                    style={{
                      position: 'absolute',
                      inset: 0,
                      background:
                        'radial-gradient(circle at 50% 50%, rgba(225,29,51,.25), transparent 70%)',
                    }}
                  />
                  <span
                    style={{
                      position: 'relative',
                      width: 26,
                      height: 26,
                      borderRadius: '50%',
                      background: 'rgba(255,255,255,.92)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                  >
                    <span
                      style={{
                        width: 0,
                        height: 0,
                        marginLeft: 3,
                        borderTop: '6px solid transparent',
                        borderBottom: '6px solid transparent',
                        borderLeft: '10px solid #0A0C11',
                      }}
                    />
                  </span>
                </span>
                <span
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 3,
                    paddingRight: 6,
                  }}
                >
                  <span style={{ fontWeight: 600, fontSize: 14.5, color: '#EEF1F5' }}>
                    Watch the Quest 3 demo
                  </span>
                  <span style={mono({ fontSize: 10.5, letterSpacing: '.14em', color: '#7C8694' })}>
                    In-headset capture · 0:42
                  </span>
                </span>
              </Link>
            </div>
          </div>

          {/* right column: calibrated honesty teaser + scroll cue (hidden on mobile —
              it's a fixed 280px card that would overflow a phone screen) */}
          <div
            style={{
              display: isMobile ? 'none' : 'flex',
              flexDirection: 'column',
              alignItems: 'flex-end',
              gap: 26,
              paddingBottom: 4,
              animation: 'sonoFade 1s ease .4s both',
            }}
          >
            <div
              style={{
                position: 'relative',
                width: 280,
                border: '1px solid rgba(255,255,255,.1)',
                borderRadius: 12,
                background: 'rgba(12,15,21,.6)',
                backdropFilter: 'blur(6px)',
                WebkitBackdropFilter: 'blur(6px)',
                padding: '16px 17px',
                overflow: 'hidden',
              }}
            >
              <div
                style={{
                  position: 'absolute',
                  top: 0,
                  left: 0,
                  width: '40%',
                  height: 1,
                  background:
                    'linear-gradient(90deg,transparent,rgba(225,29,51,.9),transparent)',
                  animation: 'sonoSweep 3.4s linear infinite',
                }}
              />
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                <span
                  style={{
                    width: 7,
                    height: 7,
                    borderRadius: '50%',
                    background: '#E11D33',
                    boxShadow: '0 0 8px rgba(225,29,51,.8)',
                  }}
                />
                <span style={mono({ fontSize: 10.5, letterSpacing: '.16em', color: '#9AA3B0' })}>
                  Calibrated honesty
                </span>
              </div>
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'baseline',
                  marginBottom: 10,
                }}
              >
                <span style={{ fontSize: 12.5, color: '#A6AEBA' }}>Ejection fraction</span>
                <span
                  style={{
                    fontFamily: FONT_DISPLAY,
                    fontWeight: 600,
                    fontSize: 16,
                    color: '#F4F6F9',
                  }}
                >
                  54%{' '}
                  <span style={{ color: '#5C6675', fontSize: 12, fontWeight: 400 }}>/ ref 56%</span>
                </span>
              </div>
              <div style={{ height: 1, background: 'rgba(255,255,255,.08)', margin: '10px 0' }} />
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
                <span style={{ fontFamily: FONT_MONO, fontSize: 11, color: '#4FA8FF', marginTop: 1 }}>
                  !
                </span>
                <span style={{ fontSize: 12, lineHeight: 1.45, color: '#8A93A1' }}>
                  Least certain: <span style={{ color: '#C7CDD6' }}>apical septal wall</span> — low
                  echo contrast in this view.
                </span>
              </div>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: '#6B7482' }}>
              <span style={mono({ fontSize: 10.5, letterSpacing: '.2em' })}>Scroll</span>
              <span style={{ display: 'inline-block', animation: 'sonoCue 1.8s ease-in-out infinite' }}>
                ↓
              </span>
            </div>
          </div>
        </div>
      </section>

      {/* ===== 2. HONESTY ===== */}
      <section
        id="honesty"
        style={{
          ...sectionBase,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'flex-end',
          padding: '120px 7vw',
        }}
      >
        <div data-reveal style={{ ...cardGlassLarge, ...revealStyle, maxWidth: 520 }}>
          <div style={eyebrow('#E1485C')}>Calibrated honesty</div>
          <h2 style={{ ...h2Style, marginBottom: 18 }}>It tells you what it can't see.</h2>
          <p style={{ fontSize: 17, lineHeight: 1.62, color: '#A6AEBA', marginBottom: 28 }}>
            Every reconstruction ships with a confidence map. Low-contrast regions — like the apical
            septal wall in an off-axis view — are flagged on the model itself, not quietly smoothed
            over. You read the anatomy and its uncertainty in the same glance.
          </p>
          <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap' }}>
            <div
              style={{
                flex: 1,
                minWidth: 130,
                border: '1px solid rgba(255,255,255,.08)',
                borderRadius: 12,
                padding: '14px 16px',
                background: 'rgba(255,255,255,.02)',
              }}
            >
              <div style={{ fontFamily: FONT_DISPLAY, fontWeight: 700, fontSize: 24, color: '#F4F6F9' }}>
                0.91
              </div>
              <div style={mono({ fontSize: 10, letterSpacing: '.14em', color: '#7C8694', marginTop: 4 })}>
                Mean confidence
              </div>
            </div>
            <div
              style={{
                flex: 1,
                minWidth: 130,
                border: '1px solid rgba(225,29,51,.22)',
                borderRadius: 12,
                padding: '14px 16px',
                background: 'rgba(225,29,51,.06)',
              }}
            >
              <div style={{ fontFamily: FONT_DISPLAY, fontWeight: 700, fontSize: 24, color: '#FF6B7E' }}>
                Apical septum
              </div>
              <div style={mono({ fontSize: 10, letterSpacing: '.14em', color: '#9AA3B0', marginTop: 4 })}>
                Flagged region
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ===== 3. HOW IT WORKS ===== */}
      <section
        id="how"
        style={{
          ...sectionBase,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '110px 7vw 30vh',
        }}
      >
        <div style={{ maxWidth: 560 }}>
          <div data-reveal style={revealStyle}>
            <div style={eyebrow()}>Pipeline</div>
            <h2 style={{ ...h2Style, marginBottom: 34 }}>From a 2D sweep to a 3D ventricle.</h2>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            {[
              {
                n: '01',
                t: 'Capture',
                d: 'A standard cardiac echo loop. No special probe, no new hardware in the room.',
              },
              {
                n: '02',
                t: 'Reconstruct',
                d: 'The model lifts the 2D frames into a temporally-consistent 3D mesh — with a confidence value at every vertex.',
              },
              {
                n: '03',
                t: 'Inhabit',
                d: 'Stream it to Quest 3 and hold the beating reconstruction at true scale in mixed reality.',
              },
            ].map((step, idx) => (
              <div
                key={step.n}
                data-reveal
                style={{
                  ...cardGlassSmall,
                  ...revealStyle,
                  display: 'flex',
                  gap: 18,
                  alignItems: 'flex-start',
                  transitionDelay: `${0.05 + idx * 0.07}s`,
                }}
              >
                <span style={{ fontFamily: FONT_MONO, fontSize: 13, color: '#E1485C', marginTop: 2 }}>
                  {step.n}
                </span>
                <div>
                  <div
                    style={{
                      fontFamily: FONT_DISPLAY,
                      fontWeight: 600,
                      fontSize: 18,
                      color: '#F4F6F9',
                      marginBottom: 5,
                    }}
                  >
                    {step.t}
                  </div>
                  <div style={{ fontSize: 14.5, lineHeight: 1.55, color: '#9AA3B0' }}>{step.d}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ===== 4. DEMO ===== */}
      <section
        id="demo"
        style={{
          ...sectionBase,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '110px 7vw 30vh',
        }}
      >
        <div data-reveal style={{ ...revealStyle, maxWidth: 540 }}>
          <div style={eyebrow()}>In-headset</div>
          <h2 style={{ ...h2Style, marginBottom: 18 }}>Grab it. Turn it. Question it.</h2>
          <p style={{ fontSize: 17, lineHeight: 1.62, color: '#A6AEBA', marginBottom: 26 }}>
            In the Quest 3 build the reconstruction sits on your desk at true scale. Walk around it,
            slice along any plane, and ask the agent to narrate what each region means — and how sure
            the model is about it.
          </p>
          {/* TODO(client): replace this placeholder with a real <video> when a file exists */}
          <div
            style={{
              position: 'relative',
              width: '100%',
              aspectRatio: '16 / 9',
              borderRadius: 14,
              overflow: 'hidden',
              border: '1px solid rgba(255,255,255,.1)',
              background: 'repeating-linear-gradient(125deg,#101319 0 10px,#15181F 10px 20px)',
            }}
          >
            <div
              style={{
                position: 'absolute',
                inset: 0,
                background:
                  'radial-gradient(circle at 50% 50%, rgba(225,29,51,.22), transparent 65%)',
              }}
            />
            <div
              style={{
                position: 'absolute',
                top: 14,
                left: 14,
                display: 'flex',
                alignItems: 'center',
                gap: 7,
              }}
            >
              <span
                style={{
                  width: 7,
                  height: 7,
                  borderRadius: '50%',
                  background: '#E11D33',
                  boxShadow: '0 0 8px rgba(225,29,51,.8)',
                  animation: 'sonoPulse 1.1s ease-in-out infinite',
                }}
              />
              <span style={mono({ fontSize: 10, letterSpacing: '.16em', color: '#C7CDD6' })}>
                REC · Quest 3
              </span>
            </div>
            <div
              style={{
                position: 'absolute',
                inset: 0,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <span
                style={{
                  width: 64,
                  height: 64,
                  borderRadius: '50%',
                  background: 'rgba(255,255,255,.92)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  boxShadow: '0 8px 30px rgba(0,0,0,.4)',
                }}
              >
                <span
                  style={{
                    width: 0,
                    height: 0,
                    marginLeft: 5,
                    borderTop: '11px solid transparent',
                    borderBottom: '11px solid transparent',
                    borderLeft: '18px solid #0A0C11',
                  }}
                />
              </span>
            </div>
            <div
              style={{
                position: 'absolute',
                bottom: 14,
                left: 14,
                right: 14,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}
            >
              <span style={mono({ fontSize: 10.5, letterSpacing: '.12em', color: '#9AA3B0' })}>
                In-headset capture
              </span>
              <span style={{ fontFamily: FONT_MONO, fontSize: 10.5, color: '#7C8694' }}>0:42</span>
            </div>
          </div>
        </div>
      </section>

      {/* ===== 5. TECH ===== */}
      <section
        id="tech"
        style={{
          ...sectionBase,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'flex-start',
          padding: '110px 7vw 30vh',
        }}
      >
        <div data-reveal style={{ ...cardGlassLarge, ...revealStyle, maxWidth: 560 }}>
          <div style={eyebrow()}>Under the hood</div>
          <h2 style={{ ...h2Style, marginBottom: 26 }}>Reconstruction you can audit.</h2>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {[
              'A temporally-consistent mesh, so the ventricle moves like one organ — not a flickering point cloud.',
              "Per-vertex confidence carried end to end — the heatmap you see is the model's own doubt.",
              "Grounded narration tied to that confidence map — it describes what's supported and refuses to fill gaps it can't see.",
              "Runs on-device on Quest 3 — no streaming a patient's scan to the cloud to look at it.",
            ].map((line, idx) => (
              <div key={idx} style={{ display: 'flex', gap: 14, alignItems: 'flex-start' }}>
                <span style={{ fontFamily: FONT_MONO, fontSize: 12, color: '#4FA8FF', marginTop: 2 }}>
                  →
                </span>
                <span style={{ fontSize: 15, lineHeight: 1.55, color: '#B4BCC8' }}>{line}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ===== 6. CLINICAL ===== */}
      <section
        id="clinical"
        style={{
          ...sectionBase,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '110px 7vw 30vh',
        }}
      >
        <div style={{ maxWidth: 560 }}>
          <div data-reveal style={revealStyle}>
            <div style={eyebrow()}>Who it's for</div>
            <h2 style={{ ...h2Style, marginBottom: 32 }}>
              For the bedside, the classroom, and the tumor board.
            </h2>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            {[
              {
                t: 'Cardiology fellows',
                d: 'Build spatial intuition for chamber geometry without waiting for a cath-lab rotation.',
              },
              {
                t: 'Pre-op planning',
                d: 'Rehearse the anatomy in three dimensions — and its uncertain regions — before you cut.',
              },
              {
                t: 'Patient consults',
                d: 'Let a patient hold their own heart and understand the plan, not just hear about it.',
              },
            ].map((card, idx) => (
              <div
                key={card.t}
                data-reveal
                style={{ ...cardGlassSmall, ...revealStyle, transitionDelay: `${0.05 + idx * 0.07}s` }}
              >
                <div
                  style={{
                    fontFamily: FONT_DISPLAY,
                    fontWeight: 600,
                    fontSize: 18,
                    color: '#F4F6F9',
                    marginBottom: 5,
                  }}
                >
                  {card.t}
                </div>
                <div style={{ fontSize: 14.5, lineHeight: 1.55, color: '#9AA3B0' }}>{card.d}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ===== 7. TEAM ===== */}
      <section
        id="team"
        style={{
          ...sectionBase,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '110px 7vw 30vh',
        }}
      >
        <div data-reveal style={{ ...revealStyle, maxWidth: 540 }}>
          <div style={eyebrow('#E1485C')}>Why we built it</div>
          <h2 style={{ ...h2Style, marginBottom: 18 }}>
            From flat grayscale loops to a heart you can hold.
          </h2>
          <p style={{ fontSize: 17, lineHeight: 1.62, color: '#A6AEBA', marginBottom: 30 }}>
            We started from a simple frustration: clinicians describe 3D anatomy to each other in
            words, over flat grayscale loops. SonoXR is our attempt to give them the object itself —
            honest about what it knows.
          </p>
          <div style={{ display: 'flex', gap: 26 }}>
            {[
              { v: '5', l: 'CAMUS studies' },
              { v: '0.91', l: 'Mean confidence' },
              { v: '0', l: 'Hallucinated walls' },
            ].map((stat) => (
              <div key={stat.l}>
                <div style={{ fontFamily: FONT_DISPLAY, fontWeight: 700, fontSize: 30, color: '#F4F6F9' }}>
                  {stat.v}
                </div>
                <div style={mono({ fontSize: 10, letterSpacing: '.14em', color: '#7C8694', marginTop: 4 })}>
                  {stat.l}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ===== 8. CTA + FOOTER ===== */}
      <section
        id="access"
        style={{
          ...sectionBase,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '120px 7vw 0',
          textAlign: 'center',
        }}
      >
        <div data-reveal style={{ ...revealStyle, maxWidth: 720 }}>
          <div style={eyebrow('#9AA3B0')}>Get access</div>
          <h2
            style={{
              ...h2Style,
              fontSize: 'clamp(34px,4vw,60px)',
              lineHeight: 1.04,
              marginBottom: 22,
            }}
          >
            See the heart you've been describing in words.
          </h2>
          <p
            style={{
              fontSize: 18,
              lineHeight: 1.58,
              color: '#A6AEBA',
              maxWidth: 560,
              margin: '0 auto 34px',
            }}
          >
            We're onboarding cardiology and imaging teams for early Quest 3 pilots. Tell us your use
            case and we'll bring a headset.
          </p>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 16,
              flexWrap: 'wrap',
            }}
          >
            <Link
              to="/login"
              className="sono-btn-primary"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 10,
                padding: '16px 30px',
                borderRadius: 10,
                background: '#E11D33',
                color: '#fff',
                fontWeight: 600,
                fontSize: 15.5,
                textDecoration: 'none',
                boxShadow: '0 8px 30px -6px rgba(225,29,51,.55)',
              }}
            >
              Open the web demo
              <span style={{ fontFamily: FONT_MONO, fontSize: 16, lineHeight: 1 }}>→</span>
            </Link>
            <Link
              to="/writeup"
              className="sono-btn-ghost"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                padding: '16px 26px',
                borderRadius: 10,
                border: '1px solid rgba(255,255,255,.14)',
                background: 'rgba(255,255,255,.03)',
                color: '#EEF1F5',
                fontWeight: 600,
                fontSize: 15.5,
                textDecoration: 'none',
              }}
            >
              Read the technical write-up
            </Link>
          </div>
        </div>
        <footer
          style={{
            marginTop: 'auto',
            width: '100%',
            borderTop: '1px solid rgba(255,255,255,.07)',
            padding: '26px 0 30px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 20,
            flexWrap: 'wrap',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 11 }}>
            <div
              style={{
                width: 11,
                height: 11,
                borderRadius: '50%',
                background: '#E11D33',
                boxShadow: '0 0 12px 2px rgba(225,29,51,.6)',
              }}
            />
            <span style={{ fontFamily: FONT_DISPLAY, fontWeight: 700, fontSize: 16, color: '#EEF1F5' }}>
              SonoXR
            </span>
            <span style={mono({ fontSize: 10.5, letterSpacing: '.16em', color: '#7C8694' })}>
              EchoAR
            </span>
          </div>
          <div style={mono({ fontSize: 10.5, letterSpacing: '.12em', color: '#6B7482', textAlign: 'center' })}>
            CAMUS dataset · Calibrated honesty layer · Voice by Deepgram
          </div>
          <div style={mono({ fontSize: 10.5, letterSpacing: '.12em', color: '#6B7482' })}>
            Built for Meta Quest 3
          </div>
        </footer>
      </section>
    </>
  )
}
