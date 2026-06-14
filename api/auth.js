export const config = { runtime: 'edge' };

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
};

export default async function handler(req) {
  if (req.method === 'OPTIONS') return new Response(null, { status: 204, headers: CORS });
  if (req.method !== 'POST') return new Response('Method not allowed', { status: 405, headers: CORS });

  let body;
  try { body = await req.json(); } catch {
    return new Response('Invalid JSON', { status: 400, headers: CORS });
  }

  const valid = body.passcode && body.passcode === process.env.IMAGE_PASSCODE;
  return new Response(JSON.stringify({ ok: valid }), {
    status: valid ? 200 : 401,
    headers: { 'Content-Type': 'application/json', ...CORS },
  });
}
