import { chromium } from 'playwright'
const b = await chromium.launch({ args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader','--ignore-gpu-blocklist'] })
const page = await b.newPage({ viewport:{width:1440,height:900} })
await page.addInitScript(() => localStorage.setItem('sonoxr_user','dr@hospital.org'))
const errs=[]; page.on('pageerror',e=>errs.push(e.message))
const url = process.argv[2] || 'http://localhost:5173/patient/patient0112'
await page.goto(url,{waitUntil:'networkidle',timeout:60000})
await page.waitForTimeout(5000)
console.log('url=', new URL(page.url()).pathname, '| errors:', errs.length?errs.join(' | '):'none')
await page.screenshot({ path: process.argv[3] || '/tmp/patient_holo.png' })
await b.close()
