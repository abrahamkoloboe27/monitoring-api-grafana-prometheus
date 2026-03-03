"""
FastAPI application monitored with Prometheus.

Routes
------
GET  /health            – liveness probe
GET  /hello             – friendly greeting
GET  /items             – list in-memory items
POST /items             – create an item
GET  /items/{item_id}   – get one item (404 if missing)
DELETE /items/{item_id} – delete one item (404 if missing)
GET  /users/me          – protected route (Bearer token required)
POST /compute           – simple arithmetic (422 on bad input)
GET  /simulate-error    – intentionally trigger various HTTP error codes
GET  /metrics           – Prometheus metrics (auto-exposed by instrumentator)
"""

import random
import time
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Monitoring Demo API",
    description="FastAPI service pre-wired for Prometheus + Grafana monitoring.",
    version="1.0.0",
)

# ---------------------------------------------------------------------------
# Prometheus instrumentation  (exposes /metrics automatically)
# ---------------------------------------------------------------------------

Instrumentator().instrument(app).expose(app)

# ---------------------------------------------------------------------------
# In-memory "database"
# ---------------------------------------------------------------------------

_items: dict[int, dict] = {
    1: {"id": 1, "name": "Laptop", "price": 999.99, "in_stock": True},
    2: {"id": 2, "name": "Mouse", "price": 29.99, "in_stock": True},
    3: {"id": 3, "name": "Keyboard", "price": 79.99, "in_stock": False},
}
_next_id = 4

# Valid API tokens (demo only – do NOT do this in production)
_VALID_TOKENS = {"secret-token-admin", "secret-token-user"}

# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class ItemCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    price: float = Field(..., gt=0)
    in_stock: bool = True


class ComputeRequest(BaseModel):
    a: float
    b: float
    operation: str = Field(..., pattern="^(add|subtract|multiply|divide)$")


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------


def get_current_token(authorization: Optional[str] = Header(default=None)) -> str:
    """Extract and validate Bearer token from Authorization header."""
    if authorization is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing",
            headers={"WWW-Authenticate": "Bearer"},
        )
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or token not in _VALID_TOKENS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or insufficient token",
        )
    return token


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health", tags=["meta"])
def health():
    """Liveness / readiness probe."""
    return {"status": "ok", "timestamp": time.time()}


@app.get("/hello", tags=["meta"])
def hello(name: str = Query(default="World")):
    """Returns a friendly greeting."""
    return {"message": f"Hello, {name}!"}


# ---- items -----------------------------------------------------------------


@app.get("/items", tags=["items"])
def list_items():
    """Return all items."""
    return {"items": list(_items.values()), "total": len(_items)}


@app.post("/items", status_code=status.HTTP_201_CREATED, tags=["items"])
def create_item(payload: ItemCreate):
    """Create a new item."""
    global _next_id
    item = {"id": _next_id, **payload.model_dump()}
    _items[_next_id] = item
    _next_id += 1
    return item


@app.get("/items/{item_id}", tags=["items"])
def get_item(item_id: int):
    """Fetch a single item by ID."""
    item = _items.get(item_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item {item_id} not found",
        )
    return item


@app.delete("/items/{item_id}", tags=["items"])
def delete_item(item_id: int):
    """Delete an item by ID."""
    item = _items.pop(item_id, None)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item {item_id} not found",
        )
    return {"deleted": item}


# ---- users -----------------------------------------------------------------


@app.get("/users/me", tags=["users"])
def get_current_user(token: str = Depends(get_current_token)):
    """Protected endpoint – requires a valid Bearer token."""
    role = "admin" if token == "secret-token-admin" else "user"
    return {"username": f"demo-{role}", "role": role, "token_preview": token[:8] + "…"}


# ---- compute ---------------------------------------------------------------


@app.post("/compute", tags=["compute"])
def compute(req: ComputeRequest):
    """Perform a simple arithmetic operation."""
    a, b, op = req.a, req.b, req.operation
    if op == "add":
        result = a + b
    elif op == "subtract":
        result = a - b
    elif op == "multiply":
        result = a * b
    else:  # divide
        if b == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Division by zero is not allowed",
            )
        result = a / b
    return {"a": a, "b": b, "operation": op, "result": result}


# ---- simulate-error --------------------------------------------------------


@app.get("/simulate-error", tags=["debug"])
def simulate_error(
    code: int = Query(
        default=500,
        description="HTTP status code to simulate (400, 401, 403, 404, 422, 500, 503)",
    )
):
    """
    Intentionally return the requested error code.
    Useful for testing alerting rules and dashboards.
    """
    allowed = {400, 401, 403, 404, 422, 500, 503}
    if code not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported code {code}. Choose from {sorted(allowed)}.",
        )
    raise HTTPException(
        status_code=code,
        detail=f"Simulated {code} error",
    )
