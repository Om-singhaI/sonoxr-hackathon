import type { VercelRequest, VercelResponse } from '@vercel/node'

// Text-to-speech via Deepgram (Aura). Returns audio/mpeg bytes the client plays.
// TODO: set DEEPGRAM_API_KEY in the Vercel project env to activate. Until then this
// returns 503 { configured: false } and the client falls back to the Web Speech API.
export const config = { maxDuration: 30 }

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
    const { text } = (req.body || {}) as { text?: string }
    if (!text) {
      res.status(400).json({ error: 'Missing text' })
      return
    }
    const dg = await fetch('https://api.deepgram.com/v1/speak?model=aura-2-thalia-en', {
      method: 'POST',
      headers: { Authorization: `Token ${apiKey}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: text.slice(0, 1800) }),
    })
    if (!dg.ok) {
      const detail = await dg.text()
      res.status(502).json({ error: 'Deepgram TTS failed', detail })
      return
    }
    const audio = Buffer.from(await dg.arrayBuffer())
    res.setHeader('Content-Type', 'audio/mpeg')
    res.setHeader('Cache-Control', 'no-store')
    res.status(200).send(audio)
  } catch (err: any) {
    console.error('[tts] error', err?.message)
    res.status(500).json({ error: 'TTS failed', detail: err?.message })
  }
}
