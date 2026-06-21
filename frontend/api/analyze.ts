import type { VercelRequest, VercelResponse } from '@vercel/node'
import Anthropic from '@anthropic-ai/sdk'

// AI analysis for the Patient Viewer — grounded in the selected patient's data.
// The ANTHROPIC_API_KEY is read server-side (never exposed to the browser).
// TODO: set ANTHROPIC_API_KEY in the Vercel project env to activate. Until then
// this returns { configured: false } and the client falls back to static text.
export const config = { maxDuration: 30 }

const SYSTEM = `You are SonoXR's cardiac analysis agent. You explain a single reconstructed
left-ventricle echo study to a clinician, grounded strictly in the structured patient data you are
given. Rules:
- Use ONLY the numbers and fields provided. Never invent measurements or anatomy.
- Be precise and concise (2–4 sentences). Speak like a careful echocardiographer.
- When the data flags low confidence or poor image quality, say so plainly and widen your
  uncertainty rather than over-committing to a crisp number.
- This is decision support for a research prototype — never give treatment instructions or a
  definitive diagnosis. It is not clinical advice.`

export default async function handler(req: VercelRequest, res: VercelResponse) {
  if (req.method !== 'POST') {
    res.status(405).json({ error: 'Method not allowed' })
    return
  }
  const apiKey = process.env.ANTHROPIC_API_KEY
  if (!apiKey) {
    // Not configured yet — let the client use its grounded fallback text.
    res.status(200).json({ configured: false })
    return
  }
  try {
    const { patient, question } = (req.body || {}) as { patient?: any; question?: string }
    if (!patient || !question) {
      res.status(400).json({ error: 'Missing patient or question' })
      return
    }
    const client = new Anthropic({ apiKey })
    const facts = {
      label: patient.label,
      ejectionFraction: patient.ef,
      edv_mL: patient.edv,
      esv_mL: patient.esv,
      imageQuality: patient.quality,
      clinicalCategory: patient.category,
      summary: patient.summary,
      flaggedUncertainty: patient.uncertainty,
    }
    const message = await client.messages.create({
      model: 'claude-opus-4-8',
      max_tokens: 1024,
      thinking: { type: 'adaptive' },
      system: SYSTEM,
      messages: [
        {
          role: 'user',
          content: `Patient data (JSON):\n${JSON.stringify(facts, null, 2)}\n\nClinician question: "${question}"\n\nAnswer grounded in the data above.`,
        },
      ],
    })
    const text = message.content
      .filter((b): b is Anthropic.TextBlock => b.type === 'text')
      .map((b) => b.text)
      .join('')
      .trim()
    res.status(200).json({ configured: true, text })
  } catch (err: any) {
    console.error('[analyze] error', err?.message)
    res.status(500).json({ error: 'Analysis failed', detail: err?.message })
  }
}
