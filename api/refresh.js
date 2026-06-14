export const config = { runtime: 'edge' };

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
};

export default async function handler(req) {
  if (req.method === 'OPTIONS') return new Response(null, { status: 204, headers: CORS });
  // Papers are fetched fresh from Gist on every request — no server-side cache to clear
  return new Response(JSON.stringify({ ok: true, message: 'Cache cleared' }), {
    headers: { 'Content-Type': 'application/json', ...CORS },
  });
}
