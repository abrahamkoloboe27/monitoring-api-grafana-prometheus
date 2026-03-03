'use strict';

/**
 * Express server for the Vue frontend.
 *
 * Responsibilities:
 *  - Serve the Vite-built static files from ./dist
 *  - Proxy /api/* requests to the FastAPI backend
 *  - Expose /metrics for Prometheus scraping (prom-client)
 */

const path = require('path');
const express = require('express');
const { createProxyMiddleware } = require('http-proxy-middleware');
const rateLimit = require('express-rate-limit');
const client = require('prom-client');

const PORT = parseInt(process.env.PORT || '3002', 10);
const API_URL = process.env.API_URL || 'http://localhost:8123';
const APP_NAME = 'vue';

// ─── Prometheus registry ───────────────────────────────────────────────────
const register = new client.Registry();
register.setDefaultLabels({ app: APP_NAME });
client.collectDefaultMetrics({ register });

const httpRequestsTotal = new client.Counter({
  name: 'frontend_http_requests_total',
  help: 'Total HTTP requests received by the frontend server',
  labelNames: ['app', 'method', 'route', 'status_code'],
  registers: [register],
});

const httpRequestDurationSeconds = new client.Histogram({
  name: 'frontend_http_request_duration_seconds',
  help: 'HTTP request duration in seconds',
  labelNames: ['app', 'method', 'route', 'status_code'],
  buckets: [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5],
  registers: [register],
});

// ─── Route normaliser (avoids high-cardinality label values) ───────────────
function normaliseRoute(url) {
  const p = url.split('?')[0];
  if (p === '/metrics') return '/metrics';
  if (p.match(/^\/api\/items\/\d+/)) return '/api/items/:id';
  if (p === '/api/items') return '/api/items';
  if (p === '/api/health') return '/api/health';
  if (p === '/api/hello') return '/api/hello';
  if (p === '/api/compute') return '/api/compute';
  if (p === '/api/users/me') return '/api/users/me';
  if (p.startsWith('/api/simulate-error')) return '/api/simulate-error';
  if (p.startsWith('/api/')) return '/api/other';
  if (p.includes('.')) return '/static';
  return '/';
}

// ─── App ───────────────────────────────────────────────────────────────────
const app = express();

// Metrics middleware
app.use((req, res, next) => {
  if (req.path === '/metrics') return next();
  const end = httpRequestDurationSeconds.startTimer();
  const route = normaliseRoute(req.originalUrl);
  res.on('finish', () => {
    const labels = {
      app: APP_NAME,
      method: req.method,
      route,
      status_code: String(res.statusCode),
    };
    httpRequestsTotal.inc(labels);
    end(labels);
  });
  next();
});

// Prometheus scrape endpoint
app.get('/metrics', async (_req, res) => {
  try {
    res.set('Content-Type', register.contentType);
    res.end(await register.metrics());
  } catch (err) {
    res.status(500).end(String(err));
  }
});

// Proxy /api/* → FastAPI backend
app.use(
  '/api',
  createProxyMiddleware({
    target: API_URL,
    changeOrigin: true,
    pathRewrite: { '^/api': '' },
    on: {
      error: (err, _req, res) => {
        console.error('[proxy error]', err.message);
        res.writeHead(502, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ detail: 'Backend unreachable' }));
      },
    },
  })
);

// Serve Vite build
const DIST = path.join(__dirname, 'dist');

// Rate-limit static file and SPA requests (mitigates DoS on filesystem access)
const staticLimiter = rateLimit({
  windowMs: 60 * 1000, // 1 minute
  max: 300,
  standardHeaders: true,
  legacyHeaders: false,
});
app.use(staticLimiter);
app.use(express.static(DIST));

// SPA fallback
app.get('*', (_req, res) => {
  res.sendFile(path.join(DIST, 'index.html'));
});

// ─── Start ─────────────────────────────────────────────────────────────────
app.listen(PORT, '0.0.0.0', () => {
  console.log(`Vue frontend listening on http://0.0.0.0:${PORT}`);
  console.log(`Prometheus metrics at http://0.0.0.0:${PORT}/metrics`);
  console.log(`Proxying /api/* -> ${API_URL}`);
});
