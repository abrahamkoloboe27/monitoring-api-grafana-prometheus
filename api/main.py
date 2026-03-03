"""
FastAPI application monitored with Prometheus.

Routes
------
GET  /health            - liveness probe
GET  /hello             - friendly greeting
GET  /items             - list in-memory items
POST /items             - create an item
GET  /items/{item_id}   - get one item (404 if missing)
DELETE /items/{item_id} - delete one item (404 if missing)
GET  /users/me          - protected route (Bearer token required)
POST /compute           - simple arithmetic (422 on bad input)
GET  /simulate-error    - intentionally trigger various HTTP error codes
GET  /metrics           - Prometheus metrics (auto-exposed by instrumentator)
"""

import logging
import sys
import time
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from loguru import logger
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------

# Remove loguru's default handler and add a cleaner one for stdout.
logger.remove()
logger.add(
    sys.stdout,
    level="DEBUG",
    format=(
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>"
    ),
    colorize=True,
)


class _InterceptHandler(logging.Handler):
    """Redirect all stdlib logging records to loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1
        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


# Wire every stdlib logger (uvicorn, fastapi, etc.) through loguru.
logging.basicConfig(handlers=[_InterceptHandler()], level=0, force=True)
for _name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
    logging.getLogger(_name).handlers = [_InterceptHandler()]
    logging.getLogger(_name).propagate = False


def _level_for_status(status_code: int) -> str:
    """Return the loguru level name appropriate for an HTTP status code."""
    if status_code >= 500:
        return "ERROR"
    if status_code >= 400:
        return "WARNING"
    return "INFO"


# ---------------------------------------------------------------------------
# Application lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application startup complete - Monitoring Demo API is ready")
    yield
    logger.info("Application shutting down")


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Monitoring Demo API",
    description="FastAPI service pre-wired for Prometheus + Grafana monitoring.",
    version="1.0.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Prometheus instrumentation  (exposes /metrics automatically)
# ---------------------------------------------------------------------------

Instrumentator().instrument(app).expose(app)

# ---------------------------------------------------------------------------
# Request / response logging middleware
# ---------------------------------------------------------------------------


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log every incoming request with its response status and duration."""
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000
    status_code = response.status_code
    msg = f"{request.method} {request.url.path} -> {status_code} ({duration_ms:.1f} ms)"
    logger.log(_level_for_status(status_code), msg)
    return response


# ---------------------------------------------------------------------------
# In-memory "database"
# ---------------------------------------------------------------------------

_items: dict[int, dict] = {
    1: {"id": 1, "name": "Laptop", "price": 999.99, "in_stock": True},
    2: {"id": 2, "name": "Mouse", "price": 29.99, "in_stock": True},
    3: {"id": 3, "name": "Keyboard", "price": 79.99, "in_stock": False},
}
_next_id = 4

# Valid API tokens (demo only - do NOT do this in production)
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
        logger.warning("Auth failed: Authorization header missing")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing",
            headers={"WWW-Authenticate": "Bearer"},
        )
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or token not in _VALID_TOKENS:
        logger.warning("Auth failed: invalid or insufficient token")
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
    logger.debug("Health check requested")
    return {"status": "ok", "timestamp": time.time()}


@app.get("/hello", tags=["meta"])
def hello(name: str = Query(default="World")):
    """Returns a friendly greeting."""
    logger.info(f"Hello requested for name={name!r}")
    return {"message": f"Hello, {name}!"}


# ---- items -----------------------------------------------------------------


@app.get("/items", tags=["items"])
def list_items():
    """Return all items."""
    logger.info(f"Listing {len(_items)} items")
    return {"items": list(_items.values()), "total": len(_items)}


@app.post("/items", status_code=status.HTTP_201_CREATED, tags=["items"])
def create_item(payload: ItemCreate):
    """Create a new item."""
    global _next_id
    item = {"id": _next_id, **payload.model_dump()}
    _items[_next_id] = item
    logger.info(f"Item created: id={_next_id} name={payload.name!r} price={payload.price}")
    _next_id += 1
    return item


@app.get("/items/{item_id}", tags=["items"])
def get_item(item_id: int):
    """Fetch a single item by ID."""
    item = _items.get(item_id)
    if item is None:
        logger.warning(f"Item not found: id={item_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item {item_id} not found",
        )
    logger.info(f"Item fetched: id={item_id}")
    return item


@app.delete("/items/{item_id}", tags=["items"])
def delete_item(item_id: int):
    """Delete an item by ID."""
    item = _items.pop(item_id, None)
    if item is None:
        logger.warning(f"Delete failed: item id={item_id} not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item {item_id} not found",
        )
    logger.info(f"Item deleted: id={item_id} name={item['name']!r}")
    return {"deleted": item}


# ---- users -----------------------------------------------------------------


@app.get("/users/me", tags=["users"])
def get_current_user(token: str = Depends(get_current_token)):
    """Protected endpoint - requires a valid Bearer token."""
    role = "admin" if token == "secret-token-admin" else "user"
    logger.info(f"User profile accessed: role={role}")
    return {"username": f"demo-{role}", "role": role, "token_preview": token[:8] + "..."}


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
            logger.warning(f"Compute error: division by zero (a={a})")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Division by zero is not allowed",
            )
        result = a / b
    logger.info(f"Compute: {a} {op} {b} = {result}")
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
        logger.warning(f"simulate-error: unsupported code {code}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported code {code}. Choose from {sorted(allowed)}.",
        )
    logger.log(_level_for_status(code), f"Simulating HTTP {code} error")
    raise HTTPException(
        status_code=code,
        detail=f"Simulated {code} error",
    )
