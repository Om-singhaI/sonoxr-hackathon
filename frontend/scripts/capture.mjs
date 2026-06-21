// Headless WebGL capture: scrolls the live app to each section, lets the camera /
// melt settle, and screenshots it. Run: node scripts/capture.mjs
import { chromium } from 'playwright'
import { mkdirSync } from 'node:fs'

const URL = process.env.URL || 'http://localhost:5173/'
const OUT = '/tmp/sono_app'
mkdirSync(OUT, { recursive: true })

// [label, sectionId, intra-section progress 0..1] — progress picks where in the
// section to sit, which sets the cinematic scalar f = index + progress.
const SHOTS = [
  ['0_hero', 'hero', 0.0],
  ['1_honesty', 'honesty', 0.4],
  ['2_how', 'how', 0.45],
  ['3_demo', 'demo', 0.45],
  ['4_tech', 'tech', 0.45],
  ['5_clinical', 'clinical', 0.4],
  ['5b_melt', 'clinical', 0.85], // heart bursting into blood
  ['6_team', 'team', 0.4], // blood pool / heart rising
  ['7_access', 'access', 0.45], // reformed whole heart
]

const browser = await chromium.launch({
  args: [
    '--use-gl=angle',
    '--use-angle=swiftshader',
    '--enable-unsafe-swiftshader',
    '--ignore-gpu-blocklist',
    '--enable-webgl',
  ],
})
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 })
page.on('console', (m) => {
  const t = m.text()
  if (m.type() === 'error') console.log('  [page error]', t)
})

console.log('navigating', URL)
await page.goto(URL, { waitUntil: 'networkidle', timeout: 60000 })

// WebGL sanity check
const gl = await page.evaluate(() => {
  const c = document.createElement('canvas')
  const g = c.getContext('webgl2') || c.getContext('webgl')
  return g ? g.getParameter(g.VERSION) : 'NO WEBGL'
})
console.log('webgl:', gl)

// wait for the heart GLB to finish loading + scene to be live
await page.waitForTimeout(6000)
await page.evaluate(() => (document.documentElement.style.scrollBehavior = 'auto'))

for (const [label, id, prog] of SHOTS) {
  await page.evaluate(
    ([id, prog]) => {
      const el = document.getElementById(id)
      window.scrollTo(0, el.offsetTop + el.offsetHeight * prog)
    },
    [id, prog],
  )
  // let camera smoothing + melt/pool + reveal-on-scroll settle
  await page.waitForTimeout(2500)
  const f = await page.evaluate(() => {
    const ids = ['hero', 'honesty', 'how', 'demo', 'tech', 'clinical', 'team', 'access']
    const vh = window.innerHeight
    let f = ids.length - 1
    const secs = ids.map((i) => document.getElementById(i))
    if (secs[0].getBoundingClientRect().top > 0) f = 0
    else
      for (let k = 0; k < secs.length; k++) {
        const r = secs[k].getBoundingClientRect()
        if (r.bottom > 0) {
          f = k + Math.min(1, Math.max(0, -r.top / (r.height || vh)))
          break
        }
      }
    return +f.toFixed(2)
  })
  const path = `${OUT}/${label}.png`
  await page.screenshot({ path })
  console.log('shot', label, 'f=', f, '->', path)
}

await browser.close()
console.log('done')
