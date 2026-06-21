import { useEffect, useRef } from 'react'
import * as THREE from 'three'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'

/**
 * HeartScene — the scroll-cinematic WebGL engine.
 *
 * One fixed full-viewport <canvas> behind the page. A single rAF loop owns the
 * renderer and reads each section's getBoundingClientRect() every frame to derive
 * a continuous scalar `f = sectionIndex + intra-section progress`. Everything —
 * camera orbit/dolly, heartbeat, the heart→particles→blood "melt", the ~3000
 * surface-sampled dissolve particles, and the fullscreen ortho blood-pool shader —
 * is a pure function of `f`.
 *
 * Ported 1:1 from the design handoff prototype (reference/SonoXR Hero.dc.html),
 * reimplemented idiomatically as a single imperative useEffect. All per-frame work
 * is kept out of React state.
 */

const SECTION_IDS = ['hero', 'honesty', 'how', 'demo', 'tech', 'clinical', 'team', 'access']

// cinematic camera keyframes per section — orbit + dolly around the heart.
// r = distance, th = azimuth, el = elevation, tx = look-target x (pans heart on screen)
const CAMS = [
  { r: 4.4, th: 0.0, el: 0.05, tx: 0.05 }, // 1 hero — straight front
  { r: 3.3, th: 0.55, el: 0.22, tx: 0.1 }, // 2 honesty — close, orbit up-right (heat visible)
  { r: 5.0, th: -0.7, el: 0.0, tx: 0.0 }, // 3 how — pull back, swing hard left
  { r: 3.5, th: 0.75, el: -0.18, tx: 0.0 }, // 4 demo — swing right + low, under the heart
  { r: 4.1, th: -0.3, el: 0.2, tx: -0.95 }, // 5 tech — heart pushed RIGHT (text sits left), zoomed out
  { r: 5.6, th: 0.2, el: 0.05, tx: 0.0 }, // 6 clinical — wide pull-back as melt begins
  { r: 5.0, th: -0.05, el: 0.1, tx: 0.0 }, // 7 team — wide, blood (heart absent/rising)
  { r: 3.8, th: 0.0, el: 0.05, tx: 0.0 }, // 8 access — settle front, heart whole
]

export default function HeartScene() {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    // ----- mutable engine state (kept out of React) -----
    let raf = 0
    let disposed = false
    let mx = 0,
      my = 0,
      tmx = 0,
      tmy = 0
    const heartShaders: any[] = []

    // Raises the camera's look-target so the heart settles vertically centered behind
    // the content (the reference frames it centered; without this it rides too high).
    const HEART_AIM_Y = 0.0
    // The echo ripple + glow should originate from behind the heart's center. The heart
    // geometry's center sits at world ≈ (-0.2, 0.35) (it's offset from the group origin,
    // and the whole world is shifted down 0.55), so place the echo there.
    const ECHO_CENTER_X = -0.2
    const ECHO_CENTER_Y = 0.9

    let w = window.innerWidth
    let h = window.innerHeight

    const renderer = new THREE.WebGLRenderer({
      canvas,
      antialias: false,
      alpha: true,
      powerPreference: 'high-performance',
    })
    // perf cap: 1.25 on retina keeps the fragment load (heart material + fullscreen
    // passes) low enough that scroll compositing stays smooth.
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.25))
    renderer.setSize(w, h, false)
    // three r152+ renames: outputColorSpace / SRGBColorSpace
    if ((THREE as any).SRGBColorSpace) renderer.outputColorSpace = (THREE as any).SRGBColorSpace
    // The prototype was authored on three 0.128 (legacy, non-physical lights). r155+
    // defaults to physically-correct lighting, which renders the same intensities far
    // dimmer — that's why the heart came out dark maroon instead of luminous pink.
    // Restore the legacy light model so the scene matches the reference brightness.
    ;(renderer as any).useLegacyLights = true
    renderer.toneMapping = THREE.ACESFilmicToneMapping
    renderer.toneMappingExposure = 0.72
    renderer.autoClear = false

    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(40, w / h, 0.1, 100)
    camera.position.set(0, 0.1, 4.4)

    // ---------- procedural environment map ----------
    const makeEnv = (): THREE.Texture | null => {
      try {
        const s = 512
        const c = document.createElement('canvas')
        c.width = s
        c.height = s / 2
        const ctx = c.getContext('2d')!
        const g = ctx.createLinearGradient(0, 0, 0, s / 2)
        g.addColorStop(0, '#323845')
        g.addColorStop(0.45, '#15181f')
        g.addColorStop(1, '#070809')
        ctx.fillStyle = g
        ctx.fillRect(0, 0, s, s / 2)
        const rg = ctx.createRadialGradient(s * 0.7, s * 0.16, 0, s * 0.7, s * 0.16, s * 0.28)
        rg.addColorStop(0, 'rgba(225,29,51,0.6)')
        rg.addColorStop(1, 'rgba(225,29,51,0)')
        ctx.fillStyle = rg
        ctx.fillRect(0, 0, s, s / 2)
        const bg = ctx.createRadialGradient(s * 0.22, s * 0.14, 0, s * 0.22, s * 0.14, s * 0.24)
        bg.addColorStop(0, 'rgba(79,168,255,0.42)')
        bg.addColorStop(1, 'rgba(79,168,255,0)')
        ctx.fillStyle = bg
        ctx.fillRect(0, 0, s, s / 2)
        const tex = new THREE.CanvasTexture(c)
        tex.mapping = THREE.EquirectangularReflectionMapping
        const pmrem = new THREE.PMREMGenerator(renderer)
        const rt = pmrem.fromEquirectangular(tex)
        tex.dispose()
        pmrem.dispose()
        return rt.texture
      } catch (e) {
        return null
      }
    }
    const env = makeEnv()
    if (env) scene.environment = env

    // ---------- lights ----------
    scene.add(new THREE.AmbientLight(0x141820, 0.5))
    scene.add(new THREE.HemisphereLight(0x2a3340, 0x140008, 0.28))
    const key = new THREE.PointLight(0xff4d62, 2.6, 30)
    key.position.set(2.4, 2.0, 3.2)
    scene.add(key)
    const fill = new THREE.PointLight(0xff3355, 1.1, 30)
    fill.position.set(-2.0, -0.6, 2.4)
    scene.add(fill)
    const rimL = new THREE.PointLight(0x4fa8ff, 2.6, 30)
    rimL.position.set(-1.4, 1.6, -3.0)
    scene.add(rimL)
    const front = new THREE.DirectionalLight(0xaeb8c6, 0.25)
    front.position.set(0.4, 0.6, 4.0)
    scene.add(front)

    // master group: holds heart + glow + blob so they shift together. We nudge the
    // whole group down (rather than tilting the camera) to vertically center the heart
    // behind the content — this keeps the echo ripple + glow locked to the heart,
    // whereas a camera tilt parallax-shifted them off-center. (Box3.setFromObject
    // centers the SkinnedMesh slightly differently in three 0.160 vs the prototype's
    // 0.128, which is why the heart otherwise rides high.)
    const world = new THREE.Group()
    world.position.y = -0.55
    scene.add(world)

    // ---------- soft radial glow plane behind the heart ----------
    const makeGlow = (rgb: number[]): THREE.Texture => {
      const s = 512
      const c = document.createElement('canvas')
      c.width = c.height = s
      const ctx = c.getContext('2d')!
      const img = ctx.createImageData(s, s)
      const d = img.data
      const cx = s / 2,
        cy = s / 2,
        R = s / 2
      const [r0, g0, b0] = rgb
      for (let y = 0; y < s; y++) {
        for (let x = 0; x < s; x++) {
          const dx = (x - cx) / R,
            dy = (y - cy) / R
          const tt = Math.sqrt(dx * dx + dy * dy)
          let a = Math.max(0, 1 - tt)
          a = Math.pow(a, 2.2)
          const noise = (Math.random() + Math.random() - 1) * 1.4
          const av = Math.max(0, Math.min(255, a * 255 + noise))
          const i = (y * s + x) * 4
          d[i] = r0
          d[i + 1] = g0
          d[i + 2] = b0
          d[i + 3] = av
        }
      }
      ctx.putImageData(img, 0, 0)
      const tex = new THREE.CanvasTexture(c)
      tex.minFilter = THREE.LinearFilter
      tex.magFilter = THREE.LinearFilter
      return tex
    }
    const glow = new THREE.Mesh(
      new THREE.PlaneGeometry(7, 7),
      new THREE.MeshBasicMaterial({
        map: makeGlow([225, 29, 51]),
        transparent: true,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      }),
    )
    glow.position.set(ECHO_CENTER_X, ECHO_CENTER_Y, -1.2)
    world.add(glow)

    // ---------- echo "blob" (pulsing lobed disc behind the heart) ----------
    const blobMat = new THREE.ShaderMaterial({
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      uniforms: {
        uColor: { value: new THREE.Color(0xff3b54) },
        uK1: { value: 3.0 },
        uK2: { value: 4.0 },
        uMix: { value: 0.0 },
        uBump: { value: 0.11 },
        uRot: { value: 0.0 },
        uRadius: { value: 0.52 },
        uFeather: { value: 0.17 },
        uOpacity: { value: 0.0 },
      },
      vertexShader:
        'varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix*modelViewMatrix*vec4(position,1.0); }',
      fragmentShader: [
        'varying vec2 vUv;',
        'uniform vec3 uColor; uniform float uK1,uK2,uMix,uBump,uRot,uRadius,uFeather,uOpacity;',
        'float hash(vec2 p){ return fract(sin(dot(p, vec2(12.9898,78.233)))*43758.5453); }',
        'void main(){',
        '  vec2 p = vUv*2.0-1.0;',
        '  float r = length(p);',
        '  float ang = atan(p.y,p.x);',
        '  float lobe = mix(cos(uK1*(ang+uRot)), cos(uK2*(ang+uRot)), uMix);',
        '  float edge = uRadius * (1.0 + uBump*lobe);',
        '  float dr = (r-edge)/uFeather;',
        '  float ring = exp(-dr*dr*0.5);',
        '  float fill = smoothstep(edge, edge-0.6, r) * 0.10;',
        '  float a = (ring + fill) * uOpacity;',
        '  a *= (1.0 - smoothstep(0.7, 1.0, r));',
        '  a += (hash(p*512.0 + uRot) - 0.5) * (2.2/255.0);',
        '  a = max(a, 0.0);',
        '  gl_FragColor = vec4(uColor*a, a);',
        '}',
      ].join('\n'),
    })
    const blob = new THREE.Mesh(new THREE.PlaneGeometry(6, 6), blobMat)
    blob.position.set(ECHO_CENTER_X, ECHO_CENTER_Y, -0.95)
    world.add(blob)

    // ---------- heart material shader injection ----------
    // uHeat lights an amber confidence highlight in the septal region;
    // uMelt fades the silhouette edges & glows hotter as it dissolves into particles.
    const injectHeartShader = (mat: any) => {
      mat.transparent = true
      mat.onBeforeCompile = (shader: any) => {
        shader.uniforms.uBuild = { value: 1 }
        shader.uniforms.uHeat = { value: 0 }
        shader.uniforms.uMelt = { value: 0 }
        shader.uniforms.uFlag = { value: new THREE.Vector3(-0.5, -0.42, 0.62) }
        shader.vertexShader =
          'uniform float uMelt;\nvarying vec3 vObjPos;\n' +
          shader.vertexShader.replace(
            '#include <begin_vertex>',
            ['#include <begin_vertex>', 'vObjPos = position;'].join('\n'),
          )
        shader.fragmentShader =
          'uniform float uHeat;\nuniform float uMelt;\nuniform vec3 uFlag;\nvarying vec3 vObjPos;\n' +
          shader.fragmentShader.replace(
            '#include <dithering_fragment>',
            [
              '#include <dithering_fragment>',
              'float _edge = pow(1.0 - clamp(dot(normalize(normal), normalize(vViewPosition)), 0.0, 1.0), 1.6);',
              'gl_FragColor.a *= (1.0 - _edge * 0.82 * uMelt);',
              'float _dm = distance(vObjPos, uFlag);',
              'float _reg = smoothstep(0.6, 0.0, _dm);',
              'gl_FragColor.rgb += uHeat * _reg * vec3(1.0,0.5,0.12) * 1.5;',
              'gl_FragColor.a = max(gl_FragColor.a, uHeat*_reg*0.55);',
              'gl_FragColor.rgb += vec3(1.0,0.22,0.18) * uMelt * 0.5;',
            ].join('\n'),
          )
        heartShaders.push(shader)
      }
      mat.needsUpdate = true
    }

    const rimMeshFor = (geometry: THREE.BufferGeometry): THREE.Mesh => {
      const rimMat = new THREE.ShaderMaterial({
        transparent: true,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
        side: THREE.FrontSide,
        uniforms: {
          uColor: { value: new THREE.Color(0xff3355) },
          uPower: { value: 2.4 },
          uInt: { value: 0.32 },
        },
        vertexShader:
          'varying vec3 vN; varying vec3 vV; void main(){ vec4 wp = modelViewMatrix*vec4(position,1.0); vN = normalize(normalMatrix*normal); vV = normalize(-wp.xyz); gl_Position = projectionMatrix*wp; }',
        fragmentShader:
          'varying vec3 vN; varying vec3 vV; uniform vec3 uColor; uniform float uPower; uniform float uInt; void main(){ float f = pow(1.0 - max(dot(vN,vV),0.0), uPower); gl_FragColor = vec4(uColor*f*uInt, f); }',
      })
      return new THREE.Mesh(geometry, rimMat)
    }

    // ---------- procedural fallback heart ----------
    let heartGroup: THREE.Group
    let heartMat: THREE.MeshStandardMaterial | null = null
    let rims: THREE.Mesh[] = []

    const buildFallbackHeart = (): THREE.Group => {
      const geo = new THREE.IcosahedronGeometry(1.08, 14)
      const pos = geo.attributes.position
      const v = new THREE.Vector3()
      for (let i = 0; i < pos.count; i++) {
        v.set(pos.getX(i), pos.getY(i), pos.getZ(i))
        const n = v.clone().normalize()
        let d = 1.0
        d += 0.11 * Math.sin(3.1 * n.x + 1.7)
        d += 0.1 * Math.sin(3.7 * n.y + 2.3 * n.z)
        d += 0.075 * Math.sin(4.3 * n.z + 1.1 * n.x)
        d += 0.05 * Math.sin(6.0 * n.y - 0.6)
        d -= 0.06 * Math.cos(2.4 * n.x - 1.9 * n.z)
        const p = n.clone().multiplyScalar(1.08 * d)
        p.y *= 1.14
        const below = Math.max(0, -n.y)
        const taper = 1 - 0.55 * Math.pow(below, 1.4)
        p.x *= taper
        p.z *= taper
        p.y -= 0.32 * Math.pow(below, 1.6)
        if (n.y > 0.35) {
          const cl = (n.y - 0.35) * 0.9
          p.y -= cl * Math.abs(Math.sin(2.6 * n.x)) * 0.4
        }
        pos.setXYZ(i, p.x, p.y, p.z)
      }
      geo.computeVertexNormals()

      const group = new THREE.Group()
      const mat = new THREE.MeshStandardMaterial({
        color: 0x3a0a14,
        emissive: 0xe11d33,
        emissiveIntensity: 0.62,
        roughness: 0.42,
        metalness: 0.05,
        flatShading: false,
      })
      heartMat = mat
      injectHeartShader(mat)
      group.add(new THREE.Mesh(geo, mat))

      const wire = new THREE.Mesh(
        geo,
        new THREE.MeshBasicMaterial({
          color: 0x4fa8ff,
          wireframe: true,
          transparent: true,
          opacity: 0.1,
        }),
      )
      wire.scale.setScalar(1.012)
      group.add(wire)

      const rimMat = new THREE.ShaderMaterial({
        transparent: true,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
        side: THREE.FrontSide,
        uniforms: {
          uColor: { value: new THREE.Color(0xff3355) },
          uPower: { value: 2.6 },
          uInt: { value: 0.9 },
        },
        vertexShader:
          'varying vec3 vN; varying vec3 vV; void main(){ vec4 wp = modelViewMatrix*vec4(position,1.0); vN = normalize(normalMatrix*normal); vV = normalize(-wp.xyz); gl_Position = projectionMatrix*wp; }',
        fragmentShader:
          'varying vec3 vN; varying vec3 vV; uniform vec3 uColor; uniform float uPower; uniform float uInt; void main(){ float f = pow(1.0 - max(dot(vN,vV),0.0), uPower); gl_FragColor = vec4(uColor*f*uInt, f); }',
      })
      const rim = new THREE.Mesh(geo, rimMat)
      rim.scale.setScalar(1.02)
      group.add(rim)

      return group
    }

    heartGroup = buildFallbackHeart()
    world.add(heartGroup)

    // ---------- background point field ----------
    const N0 = 420
    const pa = new Float32Array(N0 * 3)
    for (let i = 0; i < N0; i++) {
      const r = 2.2 + Math.random() * 3.2,
        th = Math.random() * Math.PI * 2,
        ph = Math.acos(2 * Math.random() - 1)
      pa[i * 3] = r * Math.sin(ph) * Math.cos(th)
      pa[i * 3 + 1] = r * Math.cos(ph) * 0.7
      pa[i * 3 + 2] = r * Math.sin(ph) * Math.sin(th)
    }
    const pgeo = new THREE.BufferGeometry()
    pgeo.setAttribute('position', new THREE.BufferAttribute(pa, 3))
    const points = new THREE.Points(
      pgeo,
      new THREE.PointsMaterial({
        color: 0x9fbfe6,
        size: 0.022,
        transparent: true,
        opacity: 0.45,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
        sizeAttenuation: true,
      }),
    )
    scene.add(points)

    // ---------- blood pool (ortho fullscreen shader) ----------
    const orthoScene = new THREE.Scene()
    const orthoCam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 10)
    orthoCam.position.z = 1
    const liquidMat = new THREE.ShaderMaterial({
      transparent: true,
      depthTest: false,
      depthWrite: false,
      uniforms: { uTime: { value: 0 }, uLevel: { value: 0 }, uSlosh: { value: 0 } },
      vertexShader:
        'varying vec2 vUv; void main(){ vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }',
      fragmentShader: [
        'precision mediump float;',
        'varying vec2 vUv;',
        'uniform float uTime,uLevel,uSlosh;',
        'float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1,311.7)))*43758.5453); }',
        'float noise(vec2 p){ vec2 i=floor(p),f=fract(p); f=f*f*(3.0-2.0*f); float a=hash(i),b=hash(i+vec2(1.,0.)),c=hash(i+vec2(0.,1.)),d=hash(i+vec2(1.,1.)); return mix(mix(a,b,f.x),mix(c,d,f.x),f.y); }',
        'float fbm(vec2 p){ float s=0.0,a=0.5; for(int k=0;k<3;k++){ s+=a*noise(p); p*=2.0; a*=0.5; } return s; }',
        'void main(){',
        '  float x=vUv.x, y=vUv.y;',
        '  float surf = uLevel*0.5;',
        '  surf += uSlosh*(x-0.5)*1.1;',
        '  surf += 0.010*sin(x*3.0 - uTime*0.5);',
        '  surf += 0.008*sin(x*6.0 + uTime*0.8);',
        '  surf += 0.004*sin(x*11.0 - uTime*1.2);',
        '  surf += (fbm(vec2(x*2.2, uTime*0.16))-0.5)*0.018;',
        '  float d = surf - y;',
        '  if(d < -0.012){ discard; }',
        '  float depth = clamp(d/max(surf,0.001), 0.0, 1.0);',
        '  vec3 deep = vec3(0.24,0.012,0.035);',
        '  vec3 near = vec3(0.80,0.06,0.13);',
        '  vec3 col = mix(near, deep, pow(depth,0.7));',
        '  col *= 0.80 + 0.22*fbm(vec2(x*4.0, y*5.0 - uTime*0.25));',
        '  float band = smoothstep(0.0,0.025,d) * smoothstep(0.15,0.0,d);',
        '  col += band * vec3(1.0,0.45,0.5) * 0.55;',
        '  float line = smoothstep(0.011,0.0,abs(d));',
        '  col += line * vec3(1.0,0.72,0.72) * 0.7;',
        '  float a = smoothstep(-0.005,0.007,d) * 0.99;',
        '  gl_FragColor = vec4(col, a);',
        '}',
      ].join('\n'),
    })
    const quad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), liquidMat)
    quad.frustumCulled = false
    quad.renderOrder = 0
    orthoScene.add(quad)

    // ---------- 3D dissolve particles (populated on GLB load) ----------
    let hp: THREE.Points | null = null
    let hpMat: THREE.PointsMaterial | null = null
    let hpPos: Float32Array | null = null
    let hpMeta: Float32Array | null = null
    let hpCount = 0

    let mixer: THREE.AnimationMixer | null = null
    let clipDur = 1.0
    let usingGlb = false
    let glbMats: any[] = []

    // ---------- load the real beating heart ----------
    const loader = new GLTFLoader()
    loader.load(
      'heart.glb',
      (gltf) => {
        if (disposed) return
        try {
          const m = gltf.scene
          const box = new THREE.Box3().setFromObject(m)
          const size = box.getSize(new THREE.Vector3())
          // 1.78 (vs the prototype's 2.2) — three 0.160's Box3 under-measures the
          // skinned mesh, which inflated the auto-scale; this matches the reference size.
          const s = 1.78 / (Math.max(size.x, size.y, size.z) || 1)
          m.scale.setScalar(s)
          const c = box.getCenter(new THREE.Vector3())
          m.position.sub(c.multiplyScalar(s))
          glbMats = []
          heartShaders.length = 0
          rims = []
          const meshes: THREE.Mesh[] = []
          m.traverse((o: any) => {
            if (o.isMesh) meshes.push(o)
          })
          meshes.forEach((o: any) => {
            const src = Array.isArray(o.material) ? o.material[0] : o.material
            // MeshPhysicalMaterial + clearcoat (matching the prototype) — the clearcoat
            // gives the glossy pink specular highlights that make the heart read pink
            // rather than flat deep red.
            const pm: any = new THREE.MeshPhysicalMaterial({
              // lifted + hue-shifted toward pink/magenta (was 0x7a0c1c / 0x3a0410) so
              // the heart reads rosier rather than deep blood-red
              color: 0x95182f,
              emissive: 0x49101f,
              emissiveIntensity: 0.3,
              roughness: 0.52,
              metalness: 0.0,
              clearcoat: 0.4,
              clearcoatRoughness: 0.5,
              envMapIntensity: 0.45,
            })
            if (src && src.normalMap) {
              pm.normalMap = src.normalMap
              if (src.normalScale) pm.normalScale = src.normalScale.clone()
            }
            injectHeartShader(pm)
            o.material = pm
            glbMats.push(pm)
            const rim = rimMeshFor(o.geometry)
            rim.scale.setScalar(1.008)
            rim.userData.isRim = true
            o.add(rim)
            rims.push(rim)
          })
          const wrap = new THREE.Group()
          wrap.add(m)
          world.remove(heartGroup)
          world.add(wrap)
          heartGroup = wrap
          heartMat = null

          // ---- sample 3000 surface vertices into the heart-group local space ----
          try {
            world.updateMatrixWorld(true)
            const N = 3000
            const live = new Float32Array(N * 3)
            const meta = new Float32Array(N * 4) // baseAng, baseRad, baseY, rnd
            const tmp = new THREE.Vector3()
            for (let p = 0; p < N; p++) {
              const o: any = meshes[(Math.random() * meshes.length) | 0]
              const ap = o.geometry.attributes.position
              const vi = (Math.random() * ap.count) | 0
              tmp.set(ap.getX(vi), ap.getY(vi), ap.getZ(vi))
              tmp.applyMatrix4(o.matrixWorld)
              wrap.worldToLocal(tmp)
              const vx = tmp.x,
                vy = tmp.y,
                vz = tmp.z
              live[p * 3] = vx
              live[p * 3 + 1] = vy
              live[p * 3 + 2] = vz
              meta[p * 4] = Math.atan2(vz, vx)
              meta[p * 4 + 1] = Math.sqrt(vx * vx + vz * vz)
              meta[p * 4 + 2] = vy
              meta[p * 4 + 3] = Math.random()
            }
            const pg = new THREE.BufferGeometry()
            pg.setAttribute('position', new THREE.BufferAttribute(live, 3))
            // soft round additive red sprite
            const sc = 64
            const scn = document.createElement('canvas')
            scn.width = scn.height = sc
            const sx = scn.getContext('2d')!
            const sg = sx.createRadialGradient(sc / 2, sc / 2, 0, sc / 2, sc / 2, sc / 2)
            sg.addColorStop(0, 'rgba(255,130,145,1)')
            sg.addColorStop(0.45, 'rgba(232,32,58,0.92)')
            sg.addColorStop(0.8, 'rgba(150,10,28,0.4)')
            sg.addColorStop(1, 'rgba(150,10,28,0)')
            sx.fillStyle = sg
            sx.fillRect(0, 0, sc, sc)
            const sprite = new THREE.CanvasTexture(scn)
            const pmat = new THREE.PointsMaterial({
              size: 0.07,
              map: sprite,
              transparent: true,
              opacity: 0,
              depthWrite: false,
              blending: THREE.AdditiveBlending,
              sizeAttenuation: true,
            })
            const pts3d = new THREE.Points(pg, pmat)
            pts3d.frustumCulled = false
            wrap.add(pts3d)
            hp = pts3d
            hpMat = pmat
            hpPos = live
            hpMeta = meta
            hpCount = N
          } catch (e) {
            console.warn('[SonoXR] particle build failed:', e)
          }

          if (gltf.animations && gltf.animations.length) {
            mixer = new THREE.AnimationMixer(m)
            clipDur = gltf.animations[0].duration || 1.0
            mixer.clipAction(gltf.animations[0]).play()
            usingGlb = true
          }
        } catch (err) {
          console.error('[SonoXR] glb setup threw:', err)
        }
      },
      undefined,
      (e) => {
        console.warn('[SonoXR] glb load failed, using procedural placeholder:', e)
      },
    )

    // ---------- heartbeat envelope (lub-dub) ----------
    const beat = (p: number): number => {
      const wrap = (x: number) => {
        x = x % 1
        return x < 0 ? x + 1 : x
      }
      const bump = (cc: number, ww: number) => {
        let dd = wrap(p - cc)
        if (dd > 0.5) dd -= 1
        return Math.exp(-(dd * dd) / (2 * ww * ww))
      }
      return bump(0.13, 0.05) + 0.55 * bump(0.34, 0.07)
    }

    // ---------- DOM handles ----------
    let sections: HTMLElement[] | null = null
    let dots: HTMLElement[] | null = null
    let activeDot = -1
    let ambient: HTMLElement | null = null
    let ambV: number | undefined

    // ---------- per-frame smoothed state ----------
    let envEased = 0
    let lastT: number | undefined
    let lastF: number | undefined
    let sloshV = 0
    let cx2: number | undefined,
      cy2: number | undefined,
      cz2: number | undefined,
      txS = 0,
      tyS = 0

    const clock = new THREE.Clock()
    const dpr = renderer

    // ---------- listeners ----------
    const onMouse = (e: MouseEvent) => {
      tmx = (e.clientX / window.innerWidth - 0.5) * 2
      tmy = (e.clientY / window.innerHeight - 0.5) * 2
    }
    // On phones the heart fills/overflows the tall narrow viewport, so dolly the camera
    // back a touch — this shrinks the heart and its centered echo together.
    let mobileDolly = window.matchMedia('(max-width: 768px)').matches ? 1.28 : 1
    const onResize = () => {
      w = window.innerWidth
      h = window.innerHeight
      renderer.setSize(w, h, false)
      camera.aspect = w / h
      camera.updateProjectionMatrix()
      mobileDolly = window.matchMedia('(max-width: 768px)').matches ? 1.28 : 1
    }
    window.addEventListener('mousemove', onMouse, { passive: true })
    window.addEventListener('resize', onResize)

    canvas.style.opacity = '1'

    // ---------- animation loop ----------
    const animate = () => {
      raf = requestAnimationFrame(animate)
      if (document.hidden) return // backgrounded tab — don't burn GPU

      const t = clock.getElapsedTime()
      const dt = lastT === undefined ? 0.016 : Math.min(0.05, t - lastT)
      lastT = t

      const period = 1.0
      const phase = (t % period) / period
      const pulse = beat(phase)

      const rising = pulse > envEased
      const tau = rising ? 0.045 : 0.34
      envEased += (pulse - envEased) * (1 - Math.exp(-dt / tau))
      const env2 = envEased

      // mouse parallax
      const msf = 1 - Math.exp(-dt / 0.28)
      mx += (tmx - mx) * msf
      my += (tmy - my) * msf

      // ----- f = sectionIndex + intra-section progress (measured every frame) -----
      const vh = window.innerHeight || 1
      if (!sections) {
        sections = SECTION_IDS.map((id) => document.getElementById(id)).filter(
          Boolean,
        ) as HTMLElement[]
      }
      let f = 0
      const secs = sections
      if (secs && secs.length) {
        f = secs.length - 1
        if (secs[0].getBoundingClientRect().top > 0) {
          f = 0
        } else {
          for (let k = 0; k < secs.length; k++) {
            const r = secs[k].getBoundingClientRect()
            if (r.bottom > 0) {
              f = k + Math.min(1, Math.max(0, -r.top / (r.height || vh)))
              break
            }
          }
        }
      }
      if (!isFinite(f)) f = 0

      const n = CAMS.length
      let i = Math.floor(f)
      if (i < 0) i = 0
      if (i > n - 1) i = n - 1
      let local = f - i
      if (local < 0) local = 0
      if (local > 1) local = 1
      const j = Math.min(i + 1, n - 1)
      const sm = local * local * (3 - 2 * local)
      const L = (a: number, b: number) => a + (b - a) * sm
      const C = CAMS

      const sstep = (x: number) => {
        x = Math.max(0, Math.min(1, x))
        return x * x * (3 - 2 * x)
      }
      const g2 = (cc: number, ww: number) => Math.exp(-Math.pow((f - cc) / ww, 2))

      // melt: whole through slide 5, liquefies after, reforms into the close
      let melt = 0
      if (f < 4.55) melt = 0
      else if (f < 5.6) melt = sstep((f - 4.55) / 1.05)
      else if (f < 6.7) melt = 1
      else melt = 1 - sstep((f - 6.3) / 0.7)
      const presence = 1 - melt

      // pool level: surges to swallow heart, recedes to calm pool, drains as heart reforms
      let level: number
      if (f < 4.55) level = 0
      else if (f < 5.5) level = sstep((f - 4.55) / 0.95) * 0.8
      else if (f < 6.1) level = 0.8 - sstep((f - 5.5) / 0.6) * 0.38
      else if (f < 6.5) level = 0.42
      else if (f < 6.6) level = 0.42 + sstep((f - 6.5) / 0.1) * 0.13
      else level = 0.55 - sstep((f - 6.6) / 0.4) * 0.55

      const heat = Math.min(1, g2(1.0, 0.5) * 1.1) * presence

      // slosh from scroll velocity
      if (lastF === undefined) lastF = f
      const dv = (f - lastF) * vh
      lastF = f
      const targetSlosh = Math.max(-0.09, Math.min(0.09, dv * 0.0006))
      sloshV += (targetSlosh - sloshV) * (1 - Math.exp(-dt / 0.18))
      const slosh = sloshV + 0.018 * Math.sin(t * 0.7)

      // ----- cinematic camera -----
      const r = L(C[i].r, C[j].r) * mobileDolly
      let th = L(C[i].th, C[j].th) + mx * 0.16 + Math.sin(t * 0.14) * 0.08
      let el = L(C[i].el, C[j].el) - my * 0.07 + Math.sin(t * 0.11 + 1.2) * 0.04
      const tx = L(C[i].tx || 0, C[j].tx || 0)
      const ty = L((C[i] as any).ty || 0, (C[j] as any).ty || 0)
      if (el > 0.9) el = 0.9
      if (el < -0.5) el = -0.5
      const horiz = r * Math.cos(el)
      const camx = tx + horiz * Math.sin(th)
      const camy = ty + r * Math.sin(el)
      const camz = horiz * Math.cos(th)
      if (cx2 === undefined) {
        cx2 = camx
        cy2 = camy
        cz2 = camz
        txS = tx
        tyS = ty
      }
      const cs = 1 - Math.exp(-dt / 0.22)
      cx2 += (camx - cx2) * cs
      cy2! += (camy - cy2!) * cs
      cz2! += (camz - cz2!) * cs
      txS += (tx - txS) * cs
      tyS += (ty - tyS) * cs
      camera.position.set(cx2!, cy2!, cz2!)
      camera.lookAt(txS, tyS + HEART_AIM_Y, 0)

      // heart shaders
      for (const sh of heartShaders) {
        if (sh.uniforms.uBuild) sh.uniforms.uBuild.value = 1
        if (sh.uniforms.uHeat) sh.uniforms.uHeat.value = heat
        if (sh.uniforms.uMelt) sh.uniforms.uMelt.value = melt
      }

      const meshFade = 1 - sstep((melt - 0.08) / 0.37)
      const dissolving = melt > 0.01
      const g = heartGroup
      if (g) {
        g.visible = true
        if (mixer) {
          mixer.setTime(phase * (clipDur || 1.0))
          glbMats.forEach((mm) => {
            mm.emissiveIntensity = 0.44 + env2 * 0.4 + melt * 0.55
            mm.opacity = meshFade
            // keep transparent ON permanently — toggling it at runtime is not honored
            // by three 0.160 without a recompile, which left the "melted" heart
            // rendering as a bright opaque blob. depthWrite is safe to toggle.
            mm.transparent = true
            mm.depthWrite = !dissolving
          })
          const s2 = 1 + env2 * 0.02
          g.scale.set(s2, s2, s2)
        } else if (!usingGlb) {
          const s2 = 1 + env2 * 0.05
          g.scale.set(s2, s2, s2)
          if (heartMat) {
            heartMat.emissiveIntensity = 0.44 + env2 * 0.4 + melt * 0.55
            heartMat.opacity = meshFade
            heartMat.transparent = true
            heartMat.depthWrite = !dissolving
          }
        }
        g.position.y = Math.sin(t * 0.8) * 0.05
        g.rotation.y = t * 0.05 + mx * 0.06
        g.rotation.x = Math.sin(t * 0.5) * 0.02
      }

      // 3D dissolve particles
      if (hp && hpMat && hpPos && hpMeta) {
        const pin = Math.sin(Math.min(1, melt) * Math.PI)
        hpMat.opacity = pin * 0.5
        hp.visible = pin > 0.01
        if (hp.visible) {
          const pos = hpPos,
            meta = hpMeta,
            N = hpCount
          const dir = f < 6.3 ? 1 : -1
          const falling = f < 6.3
          for (let p = 0; p < N; p++) {
            const ba = meta[p * 4],
              br = meta[p * 4 + 1],
              by = meta[p * 4 + 2],
              rr = meta[p * 4 + 3]
            let e = Math.min(1, Math.max(0, melt * 1.25 - rr * 0.25))
            e = e * e * (3 - 2 * e)
            const a = ba + (e * (1.4 + rr * 2.8) * dir + t * 0.12 * e)
            const rad = br * (1 + e * (0.35 + rr * 1.5))
            pos[p * 3] = Math.cos(a) * rad
            pos[p * 3 + 2] = Math.sin(a) * rad
            const settleY = -1.9 + rr * 0.5
            const arc = Math.sin(e * Math.PI) * (0.28 + rr * 0.55)
            const yE = Math.pow(e, 0.62)
            pos[p * 3 + 1] = by * (1 - yE) + settleY * yE + (falling ? -arc * 0.5 : arc * 0.35)
          }
          hp.geometry.attributes.position.needsUpdate = true
        }
      }

      // dark-red fresnel "skeleton" outline of the heart during the melt/blood phase
      rims.forEach((rm: any) => {
        rm.visible = dissolving
        rm.material.uniforms.uInt.value = 0.5 * melt
      })

      points.rotation.y = t * 0.02
      ;(points.material as THREE.PointsMaterial).opacity = 0.06 + 0.28 * presence

      glow.material.opacity = (0.1 + env2 * 0.14) * presence
      const gs = 1 + env2 * 0.08
      glow.scale.set(gs, gs, gs)

      {
        const u = blobMat.uniforms
        const beatIndex = Math.floor(t / period)
        const target = beatIndex % 2 === 0 ? 0.0 : 1.0
        u.uMix.value += (target - u.uMix.value) * (1 - Math.exp(-dt / 0.12))
        u.uRot.value += dt * 0.16
        u.uRadius.value = 0.46 + env2 * 0.2
        u.uBump.value = 0.04 + env2 * 0.13
        u.uOpacity.value = (0.16 + env2 * 0.5) * presence
      }

      // nav dots
      if (!dots) dots = Array.from(document.querySelectorAll('[data-navdot]'))
      if (dots && dots.length) {
        const active = Math.max(0, Math.min(dots.length - 1, Math.round(f)))
        if (active !== activeDot) {
          activeDot = active
          dots.forEach((d, idx) => {
            if (idx === active) {
              d.style.background = '#fff'
              d.style.transform = 'scale(1.7)'
              d.style.boxShadow = '0 0 10px rgba(255,255,255,.75)'
            } else {
              d.style.background = 'rgba(255,255,255,.22)'
              d.style.transform = 'scale(1)'
              d.style.boxShadow = 'none'
            }
          })
        }
      }

      // ambient red glow tracks pool/presence
      if (!ambient) ambient = document.getElementById('sono-ambient-r')
      if (ambient) {
        const targetA = 0.5 + 0.5 * Math.max(presence, level * 0.7)
        ambV = ambV === undefined ? targetA : ambV + (targetA - ambV) * 0.1
        ambient.style.opacity = ambV.toFixed(3)
      }

      // blood pool uniforms
      liquidMat.uniforms.uTime.value = t
      liquidMat.uniforms.uLevel.value = level
      liquidMat.uniforms.uSlosh.value = slosh

      // ----- two-pass render; skip the costly liquid pass when no blood on screen -----
      renderer.clear()
      renderer.render(scene, camera)
      const showLiquid = level > 0.004 || (hp ? hp.visible : false)
      if (showLiquid) renderer.render(orthoScene, orthoCam)
    }

    animate()

    // ---------- cleanup ----------
    return () => {
      disposed = true
      cancelAnimationFrame(raf)
      window.removeEventListener('mousemove', onMouse)
      window.removeEventListener('resize', onResize)
      try {
        scene.traverse((o: any) => {
          if (o.geometry) o.geometry.dispose?.()
          if (o.material) {
            const mats = Array.isArray(o.material) ? o.material : [o.material]
            mats.forEach((mm: any) => {
              mm.map?.dispose?.()
              mm.dispose?.()
            })
          }
        })
        liquidMat.dispose()
        blobMat.dispose()
        env?.dispose?.()
        renderer.dispose()
      } catch (e) {
        /* noop */
      }
      void dpr
    }
  }, [])

  return (
    <canvas
      id="sono-hero-canvas"
      ref={canvasRef}
      style={{
        position: 'fixed',
        inset: 0,
        width: '100vw',
        height: '100vh',
        zIndex: 1,
        opacity: 0,
        transition: 'opacity 1.1s ease',
        display: 'block',
      }}
    />
  )
}
