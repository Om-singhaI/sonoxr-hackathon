import { chromium } from 'playwright'
const [,, url, out, w='1440', h='900'] = process.argv
const b = await chromium.launch({ args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader','--ignore-gpu-blocklist'] })
const page = await b.newPage({ viewport:{width:+w,height:+h} })
const errs=[]; page.on('pageerror',e=>errs.push(e.message))
await page.goto(url,{waitUntil:'networkidle',timeout:60000})
await page.waitForTimeout(3500)
await page.screenshot({ path: out, fullPage: out.includes('full') })
console.log('shot', out, '| errors:', errs.length?errs.slice(0,3).join(' | '):'none')
await b.close()
