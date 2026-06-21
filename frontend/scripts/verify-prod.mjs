import { chromium } from 'playwright'
const browser = await chromium.launch({ args: ['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader','--ignore-gpu-blocklist'] })
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
const errors=[]
page.on('console', m => { if (m.type()==='error') errors.push(m.text()) })
page.on('pageerror', e => errors.push('PAGEERR '+e.message))
await page.goto('http://localhost:4173/', { waitUntil: 'networkidle', timeout: 60000 })
await page.waitForTimeout(6000)
const ok = await page.evaluate(() => ({
  sections: document.querySelectorAll('section').length,
  canvasOpacity: document.getElementById('sono-hero-canvas')?.style.opacity,
  webgl: (()=>{const c=document.createElement('canvas');return !!(c.getContext('webgl2')||c.getContext('webgl'))})(),
}))
await page.screenshot({ path: '/tmp/prod_hero.png' })
console.log('state:', JSON.stringify(ok))
console.log('errors:', errors.length? errors.join(' | ') : 'none')
await browser.close()
