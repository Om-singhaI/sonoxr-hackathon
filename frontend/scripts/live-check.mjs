import { chromium } from 'playwright'
const b = await chromium.launch({ args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader','--ignore-gpu-blocklist'] })
const base='https://sonoxr-frontend.vercel.app'
// not logged in: dashboard should bounce to login
const p1 = await b.newPage({ viewport:{width:1200,height:800} })
await p1.goto(base+'/dashboard',{waitUntil:'domcontentloaded'}); await p1.waitForTimeout(1500)
console.log('live dashboard (no auth) ->', new URL(p1.url()).pathname)
await p1.close()
// logged in: patient renders
const p2 = await b.newPage({ viewport:{width:1440,height:900} })
await p2.addInitScript(()=>localStorage.setItem('sonoxr_user','dr@hospital.org'))
const errs=[]; p2.on('pageerror',e=>errs.push(e.message))
await p2.goto(base+'/patient/patient0168',{waitUntil:'networkidle',timeout:60000}); await p2.waitForTimeout(5000)
await p2.screenshot({path:'/tmp/live_holo.png'})
console.log('live patient ->', new URL(p2.url()).pathname, '| errors:', errs.length?errs.join(' | '):'none')
await b.close()
