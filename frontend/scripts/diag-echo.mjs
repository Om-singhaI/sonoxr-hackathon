import { chromium } from 'playwright'
const b = await chromium.launch({ args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader','--ignore-gpu-blocklist'] })
const page = await b.newPage({ viewport:{width:1440,height:900} })
await page.goto('http://localhost:5173/',{waitUntil:'networkidle',timeout:60000})
await page.waitForTimeout(6500)
// force the echo blob bright and the glow bright by clamping their uniforms
await page.evaluate(() => {
  const d = window.__sonoDiag
  const bu = d.blob.material.uniforms.uOpacity
  Object.defineProperty(bu, 'value', { get(){return 0.9}, set(){}, configurable:true })
  const gm = d.glow.material
  Object.defineProperty(gm, 'opacity', { get(){return 0.9}, set(){}, configurable:true })
})
await page.waitForTimeout(500)
await page.screenshot({ path:'/tmp/echo_boosted.png' })
console.log('done')
await b.close()
