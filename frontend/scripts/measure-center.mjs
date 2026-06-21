import { chromium } from 'playwright'
const b = await chromium.launch({ args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader','--ignore-gpu-blocklist'] })
const page = await b.newPage({ viewport:{width:1440,height:900} })
await page.goto('http://localhost:5173/',{waitUntil:'networkidle',timeout:60000})
await page.waitForTimeout(6500)
const r = await page.evaluate(() => {
  const d = window.__sonoDiag, cam = d.camera, W=1440, H=900
  const toScreen = (wx,wy,wz)=>{ const v={x:wx,y:wy,z:wz}; 
    // manual project using camera matrices
    const m=cam.matrixWorldInverse.elements, p=cam.projectionMatrix.elements
    const ex=m[0]*wx+m[4]*wy+m[8]*wz+m[12], ey=m[1]*wx+m[5]*wy+m[9]*wz+m[13], ez=m[2]*wx+m[6]*wy+m[10]*wz+m[14], ew=m[3]*wx+m[7]*wy+m[11]*wz+m[15]
    const cx=p[0]*ex+p[4]*ey+p[8]*ez+p[12]*ew, cy=p[1]*ex+p[5]*ey+p[9]*ez+p[13]*ew, cw=p[3]*ex+p[7]*ey+p[11]*ez+p[15]*ew
    return { sx: Math.round((cx/cw*0.5+0.5)*W), sy: Math.round((1-(cy/cw*0.5+0.5))*H) }
  }
  const heart=d.getHeart(); heart.updateWorldMatrix(true,true)
  let ymin=1e9,ymax=-1e9, sxmin=1e9,sxmax=-1e9,symin=1e9,symax=-1e9
  heart.traverse(o=>{ if(o.isMesh||o.isSkinnedMesh){ const pa=o.geometry.attributes.position, mm=o.matrixWorld.elements
    for(let i=0;i<pa.count;i+=29){ const x=pa.getX(i),y=pa.getY(i),z=pa.getZ(i)
      const wx=mm[0]*x+mm[4]*y+mm[8]*z+mm[12], wy=mm[1]*x+mm[5]*y+mm[9]*z+mm[13], wz=mm[2]*x+mm[6]*y+mm[10]*z+mm[14]
      const s=toScreen(wx,wy,wz); if(s.sx<sxmin)sxmin=s.sx; if(s.sx>sxmax)sxmax=s.sx; if(s.sy<symin)symin=s.sy; if(s.sy>symax)symax=s.sy
    }}})
  const blobW=d.blob.getWorldPosition({setFromMatrixPosition(m){const e=m.elements;this.x=e[12];this.y=e[13];this.z=e[14];return this}})
  const bs=toScreen(blobW.x,blobW.y,blobW.z)
  return { heartScreenYcenter: Math.round((symin+symax)/2), heartScreenXcenter: Math.round((sxmin+sxmax)/2), heartSyTop: symin, heartSyBottom: symax, blobScreen: bs }
})
console.log(JSON.stringify(r))
await b.close()
