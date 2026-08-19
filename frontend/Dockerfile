FROM node:20-bookworm-slim

ARG API_ORIGIN=http://backend:8000
ENV API_ORIGIN=${API_ORIGIN}
ENV NODE_ENV=production

WORKDIR /app

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY next.config.ts tsconfig.json components.json biome.json postcss.config.mjs ./
COPY public ./public
COPY scripts ./scripts
COPY src ./src

RUN corepack enable \
    && pnpm install --frozen-lockfile \
    && pnpm build \
    && pnpm prune --prod

EXPOSE 3000

CMD ["pnpm", "start", "--hostname", "0.0.0.0", "--port", "3000"]
