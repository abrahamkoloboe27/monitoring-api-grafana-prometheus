# syntax=docker/dockerfile:1

# ── Stage 1: build the Vite app ────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

# Install ALL dependencies (including devDeps needed by Vite)
COPY package*.json ./
RUN npm ci

# Copy source and build
COPY . .
RUN npm run build

# ── Stage 2: production server ─────────────────────────────────────────────
FROM node:20-alpine

WORKDIR /app

# Install only production dependencies (express, prom-client, http-proxy-middleware)
COPY package*.json ./
RUN npm ci --omit=dev

# Copy server and built assets
COPY server.js .
COPY --from=builder /app/dist ./dist

EXPOSE 3001

CMD ["node", "server.js"]
