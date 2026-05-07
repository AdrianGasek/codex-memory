docker-compose:

version: "3.9"

services:
  api:
    build: ./infra/docker/api
    ports:
      - "8000:8000"
    volumes:
      - ./data:/data

  mcp:
    build: ./infra/docker/mcp
    ports:
      - "3333:3333"
    depends_on:
      - api