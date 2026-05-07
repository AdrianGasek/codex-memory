codex-mem/
│
├── README.md
├── docker-compose.yml
├── .env
│
├── apps/
│   ├── cli/                     # TypeScript CLI
│   │   ├── package.json
│   │   ├── tsconfig.json
│   │   └── src/
│   │       ├── index.ts
│   │       ├── commands/
│   │       │   ├── remember.ts
│   │       │   ├── query.ts
│   │       │   └── debug.ts
│   │       └── client/
│   │           └── memoryClient.ts
│   │
│   ├── mcp-server/             # MCP server (TS)
│   │   ├── package.json
│   │   └── src/
│   │       ├── server.ts
│   │       ├── routes/
│   │       │   ├── store.ts
│   │       │   ├── query.ts
│   │       │   └── delete.ts
│   │       └── middleware/
│   │
│   └── api/                    # Python API (FastAPI)
│       ├── pyproject.toml
│       └── app/
│           ├── main.py
│           ├── routes/
│           │   ├── memory.py
│           │   └── retrieval.py
│           ├── core/
│           │   ├── memory_store.py
│           │   ├── ranking.py
│           │   ├── dedup.py
│           │   └── summarizer.py
│           ├── retrieval/
│           │   ├── semantic.py
│           │   └── hybrid.py
│           ├── capture/
│           │   ├── from_diff.py
│           │   └── from_response.py
│           ├── storage/
│           │   ├── sqlite.py
│           │   └── vector.py
│           └── utils/
│
├── shared/
│   ├── schemas/                # wspólne modele (JSON)
│   │   └── memory.schema.json
│   └── prompts/
│       ├── inject_memory.txt
│       └── extract_knowledge.txt
│
├── data/                       # gitignored
│   ├── db/
│   └── vectors/
│
└── infra/
    ├── docker/
    │   ├── api.Dockerfile
    │   └── mcp.Dockerfile
    └── scripts/