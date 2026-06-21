import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  // heart.glb is large (~17MB) — let Vite serve it from public/ as a static asset.
  assetsInclude: ['**/*.glb'],
})
