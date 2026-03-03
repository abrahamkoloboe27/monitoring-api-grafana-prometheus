# Monitoring des Frontends React & Vue avec Prometheus et Grafana

Ce document explique comment les frontends React et Vue sont configurés pour être monitorés avec Prometheus et Grafana, et comment reproduire/adapter cette configuration dans vos propres projets.

---

## Table des matières

1. [Architecture générale](#architecture-générale)
2. [Configuration de l'API FastAPI](#configuration-de-lapi-fastapi)
3. [Architecture du serveur frontend (React & Vue)](#architecture-du-serveur-frontend)
4. [Métriques exposées](#métriques-exposées)
5. [Configuration Prometheus](#configuration-prometheus)
6. [Configuration Grafana](#configuration-grafana)
7. [Docker Compose – vue d'ensemble](#docker-compose--vue-densemble)
8. [Développement local sans Docker](#développement-local-sans-docker)
9. [Référence des ports](#référence-des-ports)
10. [FAQ](#faq)

---

## Architecture générale

```
Browser
  │
  ├─► http://localhost:3001  ──► Express (React frontend)  ──► /metrics  ──► Prometheus
  │       proxy /api/*  ──────────────────────────────────────────────────► FastAPI :8123
  │
  ├─► http://localhost:3002  ──► Express (Vue frontend)    ──► /metrics  ──► Prometheus
  │       proxy /api/*  ──────────────────────────────────────────────────► FastAPI :8123
  │
  ├─► http://localhost:8123  ──► FastAPI                   ──► /metrics  ──► Prometheus
  │
  ├─► http://localhost:9090  ──► Prometheus (scrape toutes les 15s)
  │
  └─► http://localhost:3000  ──► Grafana (dashboards provisionnés)
```

Chaque service expose un endpoint `/metrics` au format **Prometheus text format**. Prometheus scrape ces endpoints toutes les 15 secondes et stocke les données. Grafana interroge Prometheus pour afficher les dashboards.

---

## Configuration de l'API FastAPI

### 1. Dépendances requises

```txt
# api/requirements.txt
prometheus-fastapi-instrumentator==7.0.0
prometheus-client==0.21.1
```

### 2. Instrumenter l'application

```python
# api/main.py
from prometheus_fastapi_instrumentator import Instrumentator

app = FastAPI(...)

# Expose automatiquement /metrics avec les métriques HTTP
Instrumentator().instrument(app).expose(app)
```

`prometheus-fastapi-instrumentator` expose automatiquement :
- `http_requests_total` – compteur de requêtes par méthode, handler, status
- `http_request_duration_seconds` – histogramme des durées de réponse
- `http_requests_in_progress` – jauge des requêtes en cours

### 3. CORS (requis pour le développement local)

Quand les frontends s'exécutent sur des ports différents, il faut autoriser les requêtes cross-origin :

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3001",  # React
        "http://localhost:3002",  # Vue
        "http://localhost:5173",  # Vite dev
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

> **Note :** En production, dans Docker Compose, les frontends proxient les appels API via leur serveur Express – CORS n'est alors pas nécessaire pour les appels du navigateur vers l'API.

---

## Architecture du serveur frontend

Les applications React et Vue sont des **SPA (Single Page Applications)** buildées avec [Vite](https://vitejs.dev/). En production, elles sont servies par un **serveur Express Node.js** qui remplit trois rôles :

1. **Serveur de fichiers statiques** – sert le build Vite (`dist/`)
2. **Reverse proxy** – proxy les appels `/api/*` vers le backend FastAPI
3. **Endpoint `/metrics`** – expose les métriques au format Prometheus

### Structure des fichiers

```
frontend-react/         (ou frontend-vue/)
├── src/
│   ├── main.jsx        # Point d'entrée React (main.js pour Vue)
│   └── App.jsx         # Composant principal (App.vue pour Vue)
├── index.html          # Template HTML
├── vite.config.js      # Config Vite (proxy dev)
├── server.js           # Serveur Express + metrics
├── package.json
└── Dockerfile          # Multi-stage: build Vite → serveur Node.js
```

### server.js – pièce maîtresse du monitoring

```javascript
'use strict';
const express = require('express');
const { createProxyMiddleware } = require('http-proxy-middleware');
const client = require('prom-client');
const path = require('path');

const PORT = process.env.PORT || 3001;
const API_URL = process.env.API_URL || 'http://localhost:8123';
const APP_NAME = 'react'; // ou 'vue'

// 1. Créer un registre dédié avec label par défaut
const register = new client.Registry();
register.setDefaultLabels({ app: APP_NAME });

// 2. Métriques système Node.js (CPU, mémoire, event loop, GC…)
client.collectDefaultMetrics({ register });

// 3. Métriques HTTP personnalisées
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

const app = express();

// 4. Middleware de collecte de métriques (avant tout autre middleware)
app.use((req, res, next) => {
  if (req.path === '/metrics') return next();
  const end = httpRequestDurationSeconds.startTimer();
  const route = normaliseRoute(req.originalUrl);
  res.on('finish', () => {
    const labels = { app: APP_NAME, method: req.method, route, status_code: String(res.statusCode) };
    httpRequestsTotal.inc(labels);
    end(labels);
  });
  next();
});

// 5. Endpoint /metrics pour Prometheus
app.get('/metrics', async (_req, res) => {
  res.set('Content-Type', register.contentType);
  res.end(await register.metrics());
});

// 6. Proxy API
app.use('/api', createProxyMiddleware({ target: API_URL, changeOrigin: true, pathRewrite: { '^/api': '' } }));

// 7. Fichiers statiques + SPA fallback
app.use(express.static(path.join(__dirname, 'dist')));
app.get('*', (_req, res) => res.sendFile(path.join(__dirname, 'dist', 'index.html')));

app.listen(PORT, '0.0.0.0');
```

### Normalisation des routes

Pour éviter une cardinalité élevée dans les labels Prometheus (un label par URL avec ID unique), les routes sont normalisées :

```javascript
function normaliseRoute(url) {
  const p = url.split('?')[0];
  if (p.match(/^\/api\/items\/\d+/)) return '/api/items/:id';  // ← normalise /api/items/1, /2, /3…
  if (p === '/api/items')   return '/api/items';
  if (p === '/api/health')  return '/api/health';
  if (p.includes('.'))      return '/static';  // assets JS/CSS/images
  return '/';                                  // routes SPA
}
```

### Dockerfile multi-stage

```dockerfile
# Stage 1 : build Vite
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci                    # installe TOUTES les deps (y compris devDeps : Vite, React…)
COPY . .
RUN npm run build             # génère dist/

# Stage 2 : serveur production
FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --omit=dev         # installe seulement express, prom-client, http-proxy-middleware
COPY server.js .
COPY --from=builder /app/dist ./dist
EXPOSE 3001
CMD ["node", "server.js"]
```

---

## Métriques exposées

### Métriques système Node.js (collectDefaultMetrics)

| Métrique | Type | Description |
|----------|------|-------------|
| `process_cpu_seconds_total` | Counter | Temps CPU consommé |
| `process_resident_memory_bytes` | Gauge | Mémoire résidente |
| `nodejs_heap_size_used_bytes` | Gauge | Heap utilisé |
| `nodejs_heap_size_total_bytes` | Gauge | Heap total alloué |
| `nodejs_eventloop_lag_seconds` | Gauge | Lag de l'event loop |
| `nodejs_active_handles_total` | Gauge | Handles actifs (sockets, timers…) |
| `nodejs_gc_duration_seconds` | Histogram | Durée des garbage collections |

### Métriques HTTP personnalisées

| Métrique | Type | Labels | Description |
|----------|------|--------|-------------|
| `frontend_http_requests_total` | Counter | `app`, `method`, `route`, `status_code` | Total des requêtes reçues |
| `frontend_http_request_duration_seconds` | Histogram | `app`, `method`, `route`, `status_code` | Durée des requêtes |

Le label `app` vaut `"react"` ou `"vue"` pour distinguer les deux frontends.

### Métriques FastAPI (prometheus-fastapi-instrumentator)

| Métrique | Type | Description |
|----------|------|-------------|
| `http_requests_total` | Counter | Total requêtes par méthode/handler/status |
| `http_request_duration_seconds` | Histogram | Durées de réponse |
| `http_requests_in_progress` | Gauge | Requêtes en cours |

---

## Configuration Prometheus

### prometheus/prometheus.yml

```yaml
global:
  scrape_interval: 15s       # fréquence de scrape
  evaluation_interval: 15s   # fréquence d'évaluation des règles

scrape_configs:
  # Backend FastAPI
  - job_name: "fastapi"
    static_configs:
      - targets: ["api:8123"]   # hostname Docker Compose
    metrics_path: /metrics

  # Frontend React
  - job_name: "frontend-react"
    static_configs:
      - targets: ["frontend-react:3001"]
    metrics_path: /metrics

  # Frontend Vue
  - job_name: "frontend-vue"
    static_configs:
      - targets: ["frontend-vue:3002"]
    metrics_path: /metrics
```

**Points importants :**
- En Docker Compose, les hostnames sont les noms des services (ex: `api`, `frontend-react`)
- En dehors de Docker, utiliser `localhost:PORT` ou l'IP du serveur
- `metrics_path` doit correspondre à l'endpoint exposé (défaut Prometheus : `/metrics`)

### Vérification dans l'UI Prometheus

Ouvrir http://localhost:9090/targets – tous les targets doivent être `UP`.

Pour tester une requête PromQL :
```promql
# Taux de requêtes par app frontend
sum by (app) (rate(frontend_http_requests_total[1m]))

# Latence p99 du React frontend
histogram_quantile(0.99, sum by (le) (rate(frontend_http_request_duration_seconds_bucket{app="react"}[1m])))
```

---

## Configuration Grafana

### Datasource Prometheus (provisionnée automatiquement)

```yaml
# grafana/provisioning/datasources/prometheus.yml
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
    editable: true
```

### Dashboard provider

```yaml
# grafana/provisioning/dashboards/dashboard.yml
apiVersion: 1
providers:
  - name: "FastAPI Dashboards"
    orgId: 1
    folder: ""
    type: file
    disableDeletion: false
    updateIntervalSeconds: 10
    options:
      path: /etc/grafana/provisioning/dashboards
```

Grafana charge automatiquement tous les fichiers `.json` dans ce répertoire.

### Dashboards disponibles

| Fichier | Dashboard | Description |
|---------|-----------|-------------|
| `api-dashboard.json` | FastAPI Monitoring | Métriques de l'API backend |
| `frontend-dashboard.json` | Frontend Monitoring | Métriques des serveurs React & Vue |

### Panels du dashboard Frontend

| Panel | PromQL | Description |
|-------|--------|-------------|
| Total Requests React | `sum(increase(frontend_http_requests_total{app="react"}[5m]))` | Requêtes sur 5 min |
| Total Requests Vue | `sum(increase(frontend_http_requests_total{app="vue"}[5m]))` | Requêtes sur 5 min |
| Heap Node.js | `nodejs_heap_size_used_bytes` | Mémoire heap |
| Request Rate by App | `sum by (app) (rate(frontend_http_requests_total[1m]))` | Débit par frontend |
| Latence p50/p90/p99 | `histogram_quantile(0.XX, ...)` | Percentiles de latence |
| Event Loop Lag | `nodejs_eventloop_lag_seconds` | Lag event loop |
| CPU Usage | `rate(process_cpu_seconds_total[1m])` | Consommation CPU |
| Error Rate 4xx/5xx | `rate(frontend_http_requests_total{status_code=~"[45].."}[1m])` | Taux d'erreurs |

### Créer un dashboard manuellement dans Grafana

1. Ouvrir http://localhost:3000 (admin/admin)
2. **Connections → Data Sources** → vérifier que Prometheus est présent
3. **Dashboards → New → New Dashboard**
4. **Add visualization** → sélectionner "Prometheus"
5. Saisir une requête PromQL et configurer la visualisation

---

## Docker Compose – vue d'ensemble

```yaml
services:
  api:                    # FastAPI – port 8123
  frontend-react:         # React + Express – port 3001
  frontend-vue:           # Vue + Express   – port 3002
  prometheus:             # Prometheus      – port 9090
  grafana:                # Grafana         – port 3000
```

### Lancer la stack complète

```bash
docker compose up --build
```

### Variables d'environnement des frontends

| Variable | Valeur par défaut | Description |
|----------|-------------------|-------------|
| `PORT` | `3001` (react) / `3002` (vue) | Port d'écoute |
| `API_URL` | `http://localhost:8123` | URL de l'API backend |

Dans Docker Compose, `API_URL` est défini sur `http://api:8123` (réseau interne Docker).

---

## Développement local sans Docker

### Lancer l'API

```bash
cd api
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8123 --reload
```

### Lancer le frontend React en mode dev (Vite)

```bash
cd frontend-react
npm install
npm run dev        # Vite démarre sur http://localhost:5173
                   # /api/* est proxié vers http://localhost:8123
```

### Lancer le frontend Vue en mode dev (Vite)

```bash
cd frontend-vue
npm install
npm run dev        # Vite démarre sur http://localhost:5174
                   # /api/* est proxié vers http://localhost:8123
```

> Le proxy Vite est configuré dans `vite.config.js` :
> ```js
> server: {
>   proxy: {
>     '/api': { target: 'http://localhost:8123', changeOrigin: true, rewrite: p => p.replace(/^\/api/, '') }
>   }
> }
> ```

### Lancer le serveur Express en prod local (après build)

```bash
cd frontend-react
npm run build       # génère dist/
node server.js      # http://localhost:3001 + /metrics
```

---

## Référence des ports

| Service | URL | Description |
|---------|-----|-------------|
| FastAPI | http://localhost:8123 | API REST + `/metrics` + `/docs` |
| React Frontend | http://localhost:3001 | App React + `/metrics` |
| Vue Frontend | http://localhost:3002 | App Vue + `/metrics` |
| Prometheus | http://localhost:9090 | UI Prometheus |
| Grafana | http://localhost:3000 | Dashboards (admin/admin) |

---

## FAQ

### Pourquoi un serveur Express et pas Nginx pour servir les frontends ?

Nginx est plus performant pour servir des fichiers statiques, mais il ne peut pas exposer nativement des métriques Prometheus sur le même port. Le serveur Express permet d'avoir :
- La collecte de métriques applicatives (`prom-client`)
- Le proxy vers l'API (évite les problèmes CORS en production)
- La logique de fallback SPA

Pour un déploiement Nginx, vous pouvez utiliser [nginx-prometheus-exporter](https://github.com/nginxinc/nginx-prometheus-exporter) en sidecar.

### Le label `app` dans les métriques frontend

Les deux frontends exposent les mêmes noms de métriques (`frontend_http_requests_total`, etc.) mais avec le label `app="react"` ou `app="vue"`. Cela permet de les filtrer dans PromQL et dans Grafana.

### Ajouter des métriques métier côté frontend

Vous pouvez ajouter des compteurs personnalisés dans `server.js` :

```javascript
const itemsCreated = new client.Counter({
  name: 'frontend_items_created_total',
  help: 'Total items created via the frontend',
  labelNames: ['app'],
  registers: [register],
});
// Puis dans la route ou après le proxy :
// itemsCreated.inc({ app: APP_NAME });
```

### Comment ajouter des alertes Prometheus ?

Créer un fichier `prometheus/alerts.yml` :

```yaml
groups:
  - name: frontend_alerts
    rules:
      - alert: FrontendHighErrorRate
        expr: rate(frontend_http_requests_total{status_code=~"5.."}[5m]) > 0.1
        for: 1m
        labels:
          severity: warning
        annotations:
          summary: "High error rate on {{ $labels.app }} frontend"

      - alert: FrontendHighLatency
        expr: histogram_quantile(0.99, rate(frontend_http_request_duration_seconds_bucket[5m])) > 1
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "P99 latency > 1s on {{ $labels.app }} frontend"
```

Et référencer ce fichier dans `prometheus.yml` :

```yaml
rule_files:
  - /etc/prometheus/alerts.yml
```

### Monitoring des performances côté navigateur (RUM)

Pour monitorer les performances côté navigateur (Web Vitals, temps de chargement), vous pouvez utiliser :
- [web-vitals](https://github.com/GoogleChrome/web-vitals) + envoi vers un endpoint custom
- [OpenTelemetry Browser](https://opentelemetry.io/docs/languages/js/getting-started/browser/) pour un tracing distribué complet
- Grafana Faro (agent RUM open-source de Grafana Labs)
