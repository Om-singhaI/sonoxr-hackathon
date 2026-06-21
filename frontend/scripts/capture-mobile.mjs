import { chromium } from 'playwright'
import { mkdirSync } from 'node:fs'
mkdirSync('/tmp/sono_mobile',{recursive:true})
const b = await chromium.launch({ args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader','--ignore-gpu-blocklist'] })
const page = await b.newPage({ viewport:{width:390,height:844}, deviceScaleFactor:2, isMobile:true, hasTouch:true })
await page.goto('http://localhost:5173/',{waitUntil:'networkidle',timeout:60000})
await page.waitForTimeout(5000)
await page.evaluate(()=>document.documentElement.style.scrollBehavior='auto')
const shots=[['hero','hero',0],['honesty','honesty',0.3],['how','how',0.4],['access','access',0.4]]
for(const [label,id,p] of shots){
  await page.evaluate(([id,p])=>{const e=document.getElementById(id);window.scrollTo(0,e.offsetTop+e.offsetHeight*p)},[id,p])
  await page.waitForTimeout(1500)
  await page.screenshot({path:`/tmp/sono_mobile/${label}.png`})
}
// also report horizontal overflow
const ov = await page.evaluate(()=>({ scrollW: document.documentElement.scrollWidth, clientW: document.documentElement.clientWidth }))
console.log('overflow:', JSON.stringify(ov))
await b.close()
