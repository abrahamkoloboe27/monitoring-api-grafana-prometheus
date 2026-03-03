# monitoring-api-grafana-prometheus

A ready-to-run example of a **FastAPI** application monitored with **Prometheus** and **Grafana**, complete with a traffic-generator script that produces every kind of HTTP response code.

---

## Repository layout

```
.
├── api/
│   ├── main.py            # FastAPI application (8 routes + /metrics)
│   ├── requirements.txt
│   └── Dockerfile
├── prometheus/
│   └── prometheus.yml     # Scrape config (targets the `api` service)
├── grafana/
│   └── provisioning/
│       ├── datasources/
│       │   └── prometheus.yml   # Auto-wires Prometheus as default datasource
│       └── dashboards/
│           ├── dashboard.yml    # Dashboard provider
│           └── api-dashboard.json  # Pre-built FastAPI dashboard
├── docker-compose.yml     # Starts api + prometheus + grafana
├── load_test.py           # Continuous traffic generator
└── README.md
```

---

## Quick start

### 1 – Start the full stack

```bash
docker compose up --build
```

| Service    | URL                              | Notes                        |
|------------|----------------------------------|------------------------------|
| API        | http://localhost:8123            | FastAPI + auto-docs at `/docs` |
| Prometheus | http://localhost:9090            | Scrapes `/metrics` every 15 s |
| Grafana    | http://localhost:3000            | admin / admin                |

### 2 – Browse the API docs

Open http://localhost:8123/docs for the interactive Swagger UI.

### 3 – Generate traffic

```bash
pip install requests          # only dependency
python load_test.py           # default: 0.05 s delay, 20-req batches

# options
python load_test.py --base-url http://localhost:8123 --delay 0.1 --batch-size 50
```

The script continuously exercises every route and deliberately produces:

| Scenario | Status code |
|----------|-------------|
| Normal reads/writes | 200, 201 |
| Missing items | 404 |
| Invalid payloads | 422 |
| Missing auth header | 401 |
| Wrong/bad token | 403 |
| Division by zero | 400 |
| Simulated server errors | 500, 503 |
| API unreachable | printed as `DOWN` |

---

## API routes

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness probe |
| `GET` | `/hello?name=<name>` | Greeting |
| `GET` | `/items` | List all items |
| `POST` | `/items` | Create an item |
| `GET` | `/items/{id}` | Get one item (404 if missing) |
| `DELETE` | `/items/{id}` | Delete one item (404 if missing) |
| `GET` | `/users/me` | Protected – requires `Authorization: Bearer <token>` |
| `POST` | `/compute` | Arithmetic: add / subtract / multiply / divide |
| `GET` | `/simulate-error?code=<code>` | Intentionally return any error code |
| `GET` | `/metrics` | Prometheus metrics (auto-exposed) |

### Authentication

Two demo tokens are accepted for `/users/me`:

```
Authorization: Bearer secret-token-admin
Authorization: Bearer secret-token-user
```

---

## Grafana dashboard

The dashboard is auto-provisioned on first start. It includes:

* **Total requests** (last 5 min)
* **Error rate** (5xx)
* **Average response time**
* **Active in-flight requests**
* **Request rate by status code** (time-series)
* **Request rate by route** (time-series)
* **Latency percentiles** p50 / p90 / p99
* **4xx / 5xx error rate** (time-series)

---

## Run the API standalone (without Docker)

```bash
cd api
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8123 --reload
```