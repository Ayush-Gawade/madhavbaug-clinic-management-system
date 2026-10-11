# Multi-stage edge image: build the SPA, then serve it with Caddy which also
# reverse-proxies API traffic. Build context is the repository root.
FROM node:22-alpine AS web-build
ENV PNPM_HOME=/pnpm
ENV PATH=$PNPM_HOME:$PATH
RUN corepack enable
WORKDIR /src
COPY apps/web/package.json apps/web/pnpm-lock.yaml* ./
RUN pnpm config set dangerouslyAllowAllBuilds true \
    && (pnpm install --frozen-lockfile || pnpm install)
COPY apps/web/ ./
RUN pnpm build

FROM caddy:2-alpine
COPY infra/edge/Caddyfile /etc/caddy/Caddyfile
COPY --from=web-build /src/dist /srv
