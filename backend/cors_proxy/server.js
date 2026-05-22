/**
 * ANITorr CORS proxy.
 * GET /proxy?url=<urlencoded>           → streams response body w/ CORS headers
 * GET /resolve?url=<nyaa-magnet-page>   → returns { magnet, torrent_url, files[] }
 *
 * Why: nyaa.si and friends often block in-browser fetches; this little Express
 * service runs alongside the Flask app to yield REAL links.
 */
const express = require('express');
const cors = require('cors');
const fetch = require('node-fetch');

const app = express();
app.use(cors());
const PORT = process.env.PORT || 8787;

const UA = 'Mozilla/5.0 (ANITorr CORS Proxy)';

app.get('/proxy', async (req, res) => {
  const url = req.query.url;
  if (!url) return res.status(400).json({ error: 'missing url' });
  try {
    const r = await fetch(url, { headers: { 'User-Agent': UA }, redirect: 'follow' });
    res.set('Content-Type', r.headers.get('content-type') || 'text/html');
    const buf = await r.buffer();
    res.send(buf);
  } catch (e) { res.status(502).json({ error: e.message }); }
});

app.get('/resolve', async (req, res) => {
  const url = req.query.url;
  if (!url) return res.status(400).json({ error: 'missing url' });
  try {
    const r = await fetch(url, { headers: { 'User-Agent': UA } });
    const html = await r.text();
    const magnet = (html.match(/magnet:\?[^"' )]+/) || [''])[0];
    const torrent = (html.match(/https?:\/\/[^"']+\.torrent/) || [''])[0];
    const files = [];
    const fileRe = /<li[^>]*>([^<]+\.(?:mkv|mp4|avi|srt|ass|flac|mka))<\/li>/gi;
    let m; while ((m = fileRe.exec(html))) files.push(m[1].trim());
    res.json({ magnet, torrent_url: torrent, files });
  } catch (e) { res.status(502).json({ error: e.message }); }
});

app.get('/', (_, res) => res.json({
  ok: true, name: 'anitorr-cors-proxy',
  endpoints: ['/proxy?url=', '/resolve?url=']
}));

app.listen(PORT, () => console.log(`[anitorr-cors-proxy] listening on :${PORT}`));
