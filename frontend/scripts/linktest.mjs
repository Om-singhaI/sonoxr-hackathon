import { chromium } from 'playwright'
const b = await chromium.launch({ args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader','--ignore-gpu-blocklist'] })
const page = await b.newPage({ viewport:{width:1440,height:900} })
const errs=[]; page.on('pageerror',e=>errs.push(e.message))
const base='http://localhost:5173'
const log=(m)=>console.log(m)
// 1. landing
await page.goto(base+'/',{waitUntil:'domcontentloaded'}); await page.waitForTimeout(1500)
log('landing url='+new URL(page.url()).pathname)
// 2. top-nav Launch dashboard
await page.click('text=Launch dashboard'); await page.waitForTimeout(800)
log('after Launch dashboard -> '+new URL(page.url()).pathname)
// 3. dashboard: click first patient card (Web mode) -> /patient/:id
await page.click('text=Patient 0001'); await page.waitForTimeout(1200)
log('after click Patient 0001 -> '+new URL(page.url()).pathname)
// 4. patient: Next button
await page.click('text=Next'); await page.waitForTimeout(800)
log('after Next -> '+new URL(page.url()).pathname)
// 5. patient: Home -> dashboard
await page.click('text=Home'); await page.waitForTimeout(800)
log('after Home -> '+new URL(page.url()).pathname)
// 6. dashboard: Site -> /
await page.click('text=← Site'); await page.waitForTimeout(800)
log('after Site -> '+new URL(page.url()).pathname)
// 7. landing footer write-up
await page.goto(base+'/',{waitUntil:'domcontentloaded'}); await page.waitForTimeout(800)
await page.click('text=Read the technical write-up'); await page.waitForTimeout(800)
log('after write-up -> '+new URL(page.url()).pathname)
// 8. login flow: go to /login, fill, submit -> dashboard
await page.goto(base+'/login',{waitUntil:'domcontentloaded'}); await page.waitForTimeout(600)
await page.fill('input[type=email]','dr@hospital.org'); await page.fill('input[type=password]','test1234')
await page.click('text=Sign in & launch console'); await page.waitForTimeout(1200)
log('after login submit -> '+new URL(page.url()).pathname)
log('PAGE ERRORS: '+(errs.length?errs.join(' | '):'none'))
await b.close()
