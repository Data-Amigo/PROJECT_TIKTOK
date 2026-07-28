# SokoLink FRONTEND (Next.js 16) — deployed as its OWN Railway service.
#
# This service's Root Directory = `frontend`, so the build context IS this
# folder (paths below are relative to frontend/). Multi-stage + Next's
# standalone output keeps the runtime image small.
#
# IMPORTANT: NEXT_PUBLIC_* values are inlined into the browser bundle at BUILD
# time, so NEXT_PUBLIC_API_URL must be a Railway *build* variable, passed through
# as an ARG below — setting it only at runtime would be too late.

# ---- deps ----
FROM node:22-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

# ---- build ----
FROM node:22-slim AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN npm run build

# ---- run (standalone server) ----
FROM node:22-slim AS run
WORKDIR /app
ENV NODE_ENV=production
# Next's standalone server binds to $PORT (Railway injects it) on 0.0.0.0.
ENV HOSTNAME=0.0.0.0
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public
CMD ["node", "server.js"]
