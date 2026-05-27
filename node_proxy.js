const http = require('http');
const https = require('https');
const url = require('url');

const PORT = 18766;
const UPSTREAM_HOST = 'opencode.ai';
const UPSTREAM_PORT = 443;

const server = http.createServer((req, res) => {
  const bodyChunks = [];

  req.on('data', chunk => bodyChunks.push(chunk));
  req.on('end', () => {
    const body = Buffer.concat(bodyChunks);
    const path = req.url; // e.g. /zen/v1/chat/completions

    // Debug: log incoming request details
    const bodySample = body.length > 200 ? body.slice(0, 200).toString() + '...' : body.toString();
    console.error(`[${req.method} ${path}] len=${body.length} headers=${JSON.stringify(req.headers)} body=${bodySample}`);

    const upstreamOpts = {
      hostname: UPSTREAM_HOST,
      port: UPSTREAM_PORT,
      path: path,
      method: req.method,
      headers: {
        'Content-Type': req.headers['content-type'] || 'application/json',
        'Content-Length': body.length,
      },
    };

    // Forward Authorization header if present (some routes may need it)
    if (req.headers['authorization']) {
      upstreamOpts.headers['Authorization'] = req.headers['authorization'];
    }

    const upstreamReq = https.request(upstreamOpts, upstreamRes => {
      // Stream response headers
      const responseHeaders = { ...upstreamRes.headers };
      delete responseHeaders['transfer-encoding']; // let Node manage encoding
      res.writeHead(upstreamRes.statusCode, responseHeaders);

      // Stream response body directly
      upstreamRes.pipe(res);
    });

    upstreamReq.on('error', err => {
      console.error('Upstream error:', err.message);
      res.writeHead(502, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({
        error: { message: `Node proxy upstream error: ${err.message}`, type: 'proxy_error' },
      }));
    });

    upstreamReq.write(body);
    upstreamReq.end();
  });

  req.on('error', err => {
    console.error('Request error:', err.message);
    res.writeHead(400, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({
      error: { message: `Node proxy request error: ${err.message}`, type: 'proxy_error' },
    }));
  });
});

server.listen(PORT, '127.0.0.1', () => {
  console.error(`Node.js proxy listening on 127.0.0.1:${PORT}`);
  console.error(`Forwarding to https://${UPSTREAM_HOST}`);
});
