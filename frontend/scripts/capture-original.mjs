// Render the ORIGINAL .dc.html design (with React injected) and screenshot each
// section, so we can compare our React port against the real reference.
import { chromium } from 'playwright'
import { mkdirSync } from 'node:fs'

const URL = 'http://localhost:8099/SonoXR%20Hero.dc.html'
const OUT = '/tmp/sono_orig'
mkdirSync(OUT, { recursive: true })

const SHOTS = [
  ['0_hero', 'hero', 0.0],
  ['1_honesty', 'honesty', 0.4],
  ['2_how', 'how', 0.45],
  ['3_demo', 'demo', 0.45],
  ['4_tech', 'tech', 0.45],
  ['5_clinical', 'clinical', 0.4],
  ['5b_melt', 'clinical', 0.8],
  ['6a_blood', 'team', 0.15],
  ['6_team', 'team', 0.45],
  ['7_access', 'access', 0.45],
]

const browser = await chromium.launch({
  args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'],
})
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 })
page.on('console', (m) => { if (m.type() === 'error') console.log('  [err]', m.text()) })
page.on('pageerror', (e) => console.log('  [pageerror]', e.message))

console.log('navigating', URL)
await page.goto(URL, { waitUntil: 'networkidle', timeout: 60000 })

const boot = await page.evaluate(() => ({
  hasReact: !!window.React,
  hasReactDOM: !!window.ReactDOM,
  sections: document.querySelectorAll('section').length,
  canvas: !!document.getElementById('sono-hero-canvas'),
  h1: document.querySelector('h1') ? document.querySelector('h1').innerText.slice(0, 40) : null,
}))
console.log('boot:', JSON.stringify(boot))

await page.waitForTimeout(6000)
await page.evaluate(() => (document.documentElement.style.scrollBehavior = 'auto'))

for (const [label, id, prog] of SHOTS) {
  await page.evaluate(
    ([id, prog]) => {
      const el = document.getElementById(id)
      if (el) window.scrollTo(0, el.offsetTop + el.offsetHeight * prog)
    },
    [id, prog],
  )
  await page.waitForTimeout(2500)
  await page.screenshot({ path: `${OUT}/${label}.png` })
  console.log('shot', label)
}
await browser.close()
console.log('done')
