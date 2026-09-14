# Caddy with Cloudflare DNS challenge plugin (for TLS when the VPS is not on Cloudflare HTTP).
# Build context: infra/caddy
FROM caddy:2-builder-alpine AS builder

RUN xcaddy build \
    --with github.com/caddy-dns/cloudflare

FROM caddy:2-alpine

COPY --from=builder /usr/bin/caddy /usr/bin/caddy
