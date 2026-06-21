import type { VercelRequest, VercelResponse } from '@vercel/node'

// Speech-to-text via Deepgram (Nova). Receives raw recorded audio bytes (the
// Content-Type the browser's MediaRecorder produced, e.g. audio/webm) and returns
// { transcript }. TODO: set DEEPGRAM_API_KEY in Vercel env to activate; until then
// returns 503 { configured: false } and the client hides the mic affordance.
export const config = { maxDuration: 30 }

// We need the raw request body (binary audio), not a parsed JSON object.
function readRaw(req: VercelRequest): Promise<Buffer> {
  return new Promise((resolve, reject) => {
    const chunks: Uint8Array[] = []
    req.on('data', (c: Uint8Array) => chunks.push(c))
    req.on('end', () => resolve(Buffer.concat(chunks as any)))
    req.on('error', reject)
  })
}

export default async function handler(req: VercelRequest, res: VercelResponse) {
  if (req.method !== 'POST') {
    res.status(405).json({ error: 'Method not allowed' })
    return
  }
  const apiKey = process.env.DEEPGRAM_API_KEY
  if (!apiKey) {
    res.status(503).json({ configured: false })
    return
  }
  try {
    const audio = Buffer.isBuffer(req.body) ? req.body : await readRaw(req)
    if (!audio || audio.length === 0) {
      res.status(400).json({ error: 'No audio received' })
      return
    }
    const contentType = (req.headers['content-type'] as string) || 'audio/webm'
    const dg = await fetch('https://api.deepgram.com/v1/listen?model=nova-2&smart_format=true&punctuate=true', {
      method: 'POST',
      headers: { Authorization: `Token ${apiKey}`, 'Content-Type': contentType },
      body: audio as any,
    })
    if (!dg.ok) {
      const detail = await dg.text()
      res.status(502).json({ error: 'Deepgram STT failed', detail })
      return
    }
    const data = (await dg.json()) as any
    const transcript: string =
      data?.results?.channels?.[0]?.alternatives?.[0]?.transcript ?? ''
    res.status(200).json({ transcript })
  } catch (err: any) {
    console.error('[stt] error', err?.message)
    res.status(500).json({ error: 'STT failed', detail: err?.message })
  }
}
