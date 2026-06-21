import { chromium } from 'playwright'
const URL='https://sonoxr-frontend.vercel.app/'
const browser = await chromium.launch({ args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader','--ignore-gpu-blocklist'] })
const page = await browser.newPage({ viewport:{width:1440,height:900} })
const errs=[]; page.on('console',m=>{if(m.type()==='error')errs.push(m.text())}); page.on('pageerror',e=>errs.push('PE '+e.message))
await page.goto(URL,{waitUntil:'networkidle',timeout:60000})
await page.waitForTimeout(7000)
const s = await page.evaluate(()=>({title:document.title, sections:document.querySelectorAll('section').length, canvas:document.getElementById('sono-hero-canvas')?.style.opacity}))
await page.screenshot({path:'/tmp/live_hero.png'})
console.log('live state:', JSON.stringify(s))
console.log('errors:', errs.length?errs.join(' | '):'none')
await browser.close()
