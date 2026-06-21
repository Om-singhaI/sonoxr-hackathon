import { chromium } from 'playwright'
const browser = await chromium.launch({ args: ['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader','--ignore-gpu-blocklist'] })
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
await page.goto('http://localhost:5173/', { waitUntil: 'networkidle', timeout: 60000 })
await page.waitForTimeout(6000)
await page.evaluate(() => document.documentElement.style.scrollBehavior='auto')
await page.evaluate(()=>{const e=document.getElementById('clinical');window.scrollTo(0,e.offsetTop+e.offsetHeight*0.8)})
await page.waitForTimeout(2200)
await page.screenshot({ path: '/tmp/sono_app/test_A_before.png' })
// hide all SkinnedMeshes (animate only toggles the parent group, not the mesh)
await page.evaluate(() => {
  let n=0
  window.__scene.traverse(o => { if (o.isSkinnedMesh){ o.visible=false; n++ } })
  window.__hidCount = n
})
await page.waitForTimeout(800)
await page.screenshot({ path: '/tmp/sono_app/test_B_skinnedHidden.png' })
console.log('skinned hidden count:', await page.evaluate(()=>window.__hidCount))
await browser.close()
