import { chromium } from 'playwright'
const b = await chromium.launch({ args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader','--ignore-gpu-blocklist'] })
// fresh context, NOT logged in
const page = await b.newPage({ viewport:{width:1200,height:800} })
await page.goto('http://localhost:5173/dashboard',{waitUntil:'domcontentloaded'}); await page.waitForTimeout(1200)
console.log('dashboard (no auth) ->', new URL(page.url()).pathname)
await page.goto('http://localhost:5173/patient/patient0001',{waitUntil:'domcontentloaded'}); await page.waitForTimeout(1000)
console.log('patient (no auth) ->', new URL(page.url()).pathname)
// now log in and confirm it lands on the protected page
await page.fill('input[type=email]','dr@hospital.org'); await page.fill('input[type=password]','test1234')
await page.click('text=Sign in & launch console'); await page.waitForTimeout(1500)
console.log('after login ->', new URL(page.url()).pathname)
await b.close()
