FROM oven/bun:1.3

WORKDIR /repo

COPY package.json tsconfig.base.json /repo/
COPY apps/cli /repo/apps/cli
COPY apps/mcp-server /repo/apps/mcp-server

RUN bun install --frozen-lockfile || bun install

CMD ["bun", "run", "apps/mcp-server/src/server.ts"]
