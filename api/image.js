export const config = { runtime: 'edge' };

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
};

export default async function handler(req) {
  if (req.method === 'OPTIONS') return new Response(null, { status: 204, headers: CORS });
  if (req.method !== 'POST') return new Response('Send POST /api/image', { status: 405, headers: CORS });

  let body;
  try { body = await req.json(); } catch {
    return new Response('Invalid JSON', { status: 400, headers: CORS });
  }

  const prompt = (body.prompt || '').trim();
  if (!prompt) return new Response(
    JSON.stringify({ error: 'prompt required' }),
    { status: 400, headers: { 'Content-Type': 'application/json', ...CORS } }
  );

  const resp = await fetch('https://apihub.agnes-ai.com/v1/images/generations', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${process.env.AGNES_KEY}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ model: 'agnes-image-2.1-flash', prompt, n: 1, size: '1024x1024' }),
  });

  const data = await resp.json();
  return new Response(JSON.stringify(data), {
    status: resp.ok ? 200 : 502,
    headers: { 'Content-Type': 'application/json', ...CORS },
  });
}
