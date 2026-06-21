import { chromium } from 'playwright'
const b = await chromium.launch({ args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader','--ignore-gpu-blocklist'] })
const page = await b.newPage({ viewport:{width:1280,height:840} })
const errs=[]; page.on('pageerror',e=>errs.push(e.message))
await page.goto('http://localhost:5173/login',{waitUntil:'domcontentloaded'}); await page.waitForTimeout(800)
await page.click('text=Use sample admin'); await page.waitForTimeout(300)
await page.click('text=Sign in & launch console'); await page.waitForTimeout(1500)
const path = new URL(page.url()).pathname
const role = await page.evaluate(()=>localStorage.getItem('sonoxr_role'))
const adminBadge = await page.evaluate(()=> [...document.querySelectorAll('span')].some(s=>s.textContent==='Admin'))
await page.screenshot({path:'/tmp/admin_dash.png'})
console.log(JSON.stringify({ path, role, adminBadge, errors: errs.length?errs:'none' }))
await b.close()
