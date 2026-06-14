export const config = { runtime: 'edge' };

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
};

export default async function handler(req) {
  if (req.method === 'OPTIONS') return new Response(null, { status: 204, headers: CORS });
  if (req.method !== 'POST') return new Response('Send POST /api/chat', { status: 405, headers: CORS });

  let body;
  try { body = await req.json(); } catch {
    return new Response('Invalid JSON', { status: 400, headers: CORS });
  }

  const messages  = Array.isArray(body.messages) ? body.messages : [];
  const systemPrompt = process.env.SYSTEM_PROMPT || 'You are Jayce, a helpful AI assistant on Jiaen Lin\'s personal research website.';

  const aiResp = await fetch('https://apihub.agnes-ai.com/v1/chat/completions', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${process.env.AGNES_KEY}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      model: 'agnes-2.0-flash',
      messages: [
        { role: 'system', content: systemPrompt },
        ...messages.slice(-12),
      ],
      stream: true,
    }),
  });

  if (!aiResp.ok) {
    const err = await aiResp.text();
    return new Response(JSON.stringify({ error: err }), {
      status: 502,
      headers: { 'Content-Type': 'application/json', ...CORS },
    });
  }

  return new Response(aiResp.body, {
    headers: { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache', ...CORS },
  });
}
