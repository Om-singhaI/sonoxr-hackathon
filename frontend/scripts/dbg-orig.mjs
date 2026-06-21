import { chromium } from 'playwright'
const browser = await chromium.launch({ args: ['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader','--ignore-gpu-blocklist'] })
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
await page.goto('http://localhost:8099/SonoXR%20Hero.dc.html', { waitUntil: 'networkidle', timeout: 60000 })
await page.waitForTimeout(6000)
await page.evaluate(() => document.documentElement.style.scrollBehavior='auto')
for (const [id,prog] of [['clinical',0.8],['team',0.15]]) {
  await page.evaluate(([id,prog])=>{const e=document.getElementById(id);window.scrollTo(0,e.offsetTop+e.offsetHeight*prog)},[id,prog])
  await page.waitForTimeout(2200)
  const s = await page.evaluate(() => {
    const o = window.__sono; if(!o) return 'no __sono'
    return {
      hpMatOpacity: o.hpMat ? +o.hpMat.opacity.toFixed(3) : null,
      hpVisible: o.hp ? o.hp.visible : null,
      glbMat0op: o.glbMats && o.glbMats[0] ? +o.glbMats[0].opacity.toFixed(3) : null,
      glbMat0emis: o.glbMats && o.glbMats[0] ? +o.glbMats[0].emissiveIntensity.toFixed(2) : null,
      glbMat0transparent: o.glbMats && o.glbMats[0] ? o.glbMats[0].transparent : null,
      rimCount: o._rims ? o._rims.length : null,
      rim0uInt: o._rims && o._rims[0] ? +o._rims[0].material.uniforms.uInt.value.toFixed(3) : null,
      rim0visible: o._rims && o._rims[0] ? o._rims[0].visible : null,
      heartChildren: o.heartGroup ? o.heartGroup.children.length : null,
    }
  })
  console.log(id, prog, JSON.stringify(s))
}
await browser.close()
