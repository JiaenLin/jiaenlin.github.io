export const config = { runtime: 'edge' };

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
};

function getSGTDate() {
  return new Date(Date.now() + 8 * 3_600_000).toISOString().slice(0, 10);
}
function getSGTHour() {
  return new Date(Date.now() + 8 * 3_600_000).getUTCHours();
}

export default async function handler(req) {
  if (req.method === 'OPTIONS') return new Response(null, { status: 204, headers: CORS });

  try {
    const gistResp = await fetch(`https://api.github.com/gists/${process.env.GIST_ID}`, {
      headers: {
        'Authorization': `Bearer ${process.env.GH_TOKEN}`,
        'Accept': 'application/vnd.github+json',
        'User-Agent': 'jiaenlin-worker',
      },
    });
    if (!gistResp.ok) throw new Error('Gist fetch failed: ' + gistResp.status);
    const gist = await gistResp.json();
    const data = JSON.parse(gist.files['paper_digest.json'].content);

    const today     = getSGTDate();
    const hour      = getSGTHour();
    const yesterday = new Date(Date.now() + 8 * 3_600_000 - 86_400_000).toISOString().slice(0, 10);
    const isValid   = data.date === today || (hour < 9 && data.date === yesterday);

    if (!isValid) {
      return new Response(JSON.stringify({
        ready: false,
        message: `Today's digest isn't ready yet — fetched at 9 AM SGT. Last update: ${data.date}`,
      }), { headers: { 'Content-Type': 'application/json', ...CORS } });
    }

    // Build the prompt from all one-sentence summaries
    const summaries = data.papers.map((p, i) => `${i + 1}. [${p.journal}] ${p.summary}`).join('\n');
    const prompt = `You are a research assistant synthesizing today's paper digest for a computational biologist (Jiaen Lin) who works in single-cell RNA-seq, multi-omics, and AI for biology. Below are the one-sentence summaries of today's papers. Write a concise, insightful "What's Happening Today" overview (3-5 sentences, in plain English, no markdown) that connects the themes across these papers and highlights what's notable for someone in computational biology / bioinformatics. Keep it informative but friendly.

${summaries}

Now write the overview:`;

    // Call Agnes AI with a 15s timeout (33 papers = large prompt)
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15_000);

    let overallSummary = '';
    try {
      const aiResp = await fetch('https://apihub.agnes-ai.com/v1/chat/completions', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${process.env.AGNES_KEY}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          model: 'agnes-2.0-flash',
          messages: [
            { role: 'system', content: 'You are a concise, insightful research summarizer. Respond in plain text without markdown formatting.' },
            { role: 'user', content: prompt },
          ],
          max_tokens: 400,
          temperature: 0.6,
          stream: false,
        }),
        signal: controller.signal,
      });
      clearTimeout(timeout);

      if (aiResp.ok) {
        const aiJson = await aiResp.json();
        overallSummary = aiJson.choices?.[0]?.message?.content?.trim() || '';
      }
    } catch (_) {
      clearTimeout(timeout);
      /* AI call failed or timed out — fallback below will handle it */
    }

    // Fallback if AI call fails or returns empty
    if (!overallSummary) {
      const journals = [...new Set(data.papers.map(p => p.journal))].join(', ');
      overallSummary = `Today's digest covers ${data.count} papers across ${journals}. Key themes emerging from today's research include advances in computational methods and biological discoveries relevant to multi-omics and single-cell analysis.`;
    }

    return new Response(JSON.stringify({
      ready: true,
      date: data.date,
      count: data.count,
      overallSummary,
      papers: data.papers,
    }), { headers: { 'Content-Type': 'application/json', ...CORS } });

  } catch (e) {
    return new Response(JSON.stringify({ ready: false, message: 'Could not fetch papers: ' + e.message }), {
      status: 500, headers: { 'Content-Type': 'application/json', ...CORS },
    });
  }
}
