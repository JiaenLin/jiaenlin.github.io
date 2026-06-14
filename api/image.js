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

  // Passcode gate
  if (!body.passcode || body.passcode !== process.env.IMAGE_PASSCODE) {
    return new Response(JSON.stringify({ error: 'Invalid access code' }), {
      status: 401,
      headers: { 'Content-Type': 'application/json', ...CORS },
    });
  }

  const prompt = (body.prompt || '').trim();
  if (!prompt) return new Response(
    JSON.stringify({ error: 'prompt required' }),
    { status: 400, headers: { 'Content-Type': 'application/json', ...CORS } }
  );

  const enc = new TextEncoder();
  const { readable, writable } = new TransformStream();
  const writer = writable.getWriter();

  // Return stream immediately so Vercel sees a response — Agnes runs in the background
  (async () => {
    // Send SSE comment pings every 5s to keep the connection alive
    let finished = false;
    const ping = setInterval(() => {
      if (!finished) writer.write(enc.encode(': ping\n\n'));
    }, 5000);

    try {
      const resp = await fetch('https://apihub.agnes-ai.com/v1/images/generations', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${process.env.AGNES_KEY}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ model: 'agnes-image-2.1-flash', prompt, n: 1, size: '1024x1024' }),
      });
      const data = await resp.json();
      const payload = resp.ok ? { ok: true, ...data } : { ok: false, error: JSON.stringify(data) };
      await writer.write(enc.encode(`data: ${JSON.stringify(payload)}\n\n`));
    } catch (e) {
      await writer.write(enc.encode(`data: ${JSON.stringify({ ok: false, error: e.message })}\n\n`));
    } finally {
      finished = true;
      clearInterval(ping);
      await writer.close();
    }
  })();

  return new Response(readable, {
    headers: { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache', ...CORS },
  });
}
