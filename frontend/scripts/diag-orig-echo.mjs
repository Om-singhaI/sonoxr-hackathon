import { chromium } from 'playwright'
const b = await chromium.launch({ args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader','--ignore-gpu-blocklist'] })
const page = await b.newPage({ viewport:{width:1440,height:900} })
await page.goto('http://localhost:8099/SonoXR%20Hero.dc.html',{waitUntil:'networkidle',timeout:60000})
await page.waitForTimeout(6500)
const info = await page.evaluate(() => {
  const o = window.__sono
  const out = { hasBlob: !!o.blob, blobPos: o.blob && [+o.blob.position.x.toFixed(2),+o.blob.position.y.toFixed(2),+o.blob.position.z.toFixed(2)],
    glowPos: o.glow && [+o.glow.position.x.toFixed(2),+o.glow.position.y.toFixed(2),+o.glow.position.z.toFixed(2)],
    worldPos: o.world && [+o.world.position.x.toFixed(2),+o.world.position.y.toFixed(2),+o.world.position.z.toFixed(2)] }
  // boost
  if (o.blobMat) Object.defineProperty(o.blobMat.uniforms.uOpacity,'value',{get(){return 0.9},set(){},configurable:true})
  if (o.glow) Object.defineProperty(o.glow.material,'opacity',{get(){return 0.9},set(){},configurable:true})
  return out
})
console.log('orig:', JSON.stringify(info))
await page.waitForTimeout(500)
await page.screenshot({ path:'/tmp/echo_orig_boosted.png' })
await b.close()
