Linki do repo Claude Code memory:
https://github.com/thedotmack/claude-mem

Dokumentacja codexa:
https://developers.openai.com/codex


Cel:
Stworzyć kopie claude-mem ale pod Codexa, najlepiej napisaną od zera nowymi technologiami, najlepszym stackiem, super wydajną i ultra efektywną.

🧠 Najważniejszy insight

👉 nie budujesz „systemu pamięci”

👉 budujesz:

nawyk korzystania z pamięci przez agenta


Stworzyć system pamięci dla agentów w Codex, który:

zapamiętuje kontekst między sesjami
zapisuje wiedzę projektową
wpływa na prompt bez ręcznego wklejania
działa automatycznie (zero friction)
👉 czyli dokładnie to, co robi claude-mem, tylko w stacku Codexa

🧩 Problem (który rozwiązujesz)

Codex:

❌ nie ma natywnej trwałej pamięci projektowej
❌ nie pamięta decyzji architektonicznych
❌ nie przechowuje preferencji usera

Efekt:

Każda sesja = reset wiedzy

👉 Codex-Mem rozwiązuje to przez:

warstwę pamięci + automatyczny injection do promptu

🏗️ Architektura (high-level)
[User / Codex UI]
        ↓
[Prompt Builder]
        ↓
[Memory Loader] ← pliki pamięci (SOUL / MEMORY / PROJECT)
        ↓
[Codex Agent]
        ↓
[Memory Extractor]
        ↓
[Memory Store (pliki / DB)]

Struktura plików (core)
.codex/
 ├── MEMORY.md        # fakty, decyzje, stan projektu
 ├── SOUL.md          # zasady, styl, preferencje
 ├── CONTEXT.md       # aktualny kontekst roboczy
 ├── HISTORY.json     # historia interakcji (opcjonalnie)
 └── INDEX.json       # szybkie lookupy

 🧠 Storage (gdzie trzymać pamięć)
 ADVANCED:
vector DB (np. embeddingi)
pgvector?

🔥 Feature’y (roadmap)
v1 (MVP)
MEMORY.md + SOUL.md
ręczny extractor
CLI wrapper
v2
automatyczny extractor (regex + heurystyki)
ranking ważności pamięci
v3
embeddings + semantic search
auto-trim (context limit)

1. context window

👉 nie możesz wrzucać wszystkiego

rozwiązanie:

top-N memory
summarization
2. garbage memory

👉 model zapisze śmieci

rozwiązanie:

filtr:
tylko decyzje
tylko fakty
ignore small talk
3. konflikty pamięci

👉 stare vs nowe

rozwiązanie:

latest wins + log zmian

🔧 Stack sugerowany
Node.js / Bun
Markdown parser
OpenAI API (Codex)
opcjonalnie:
embeddings
SQLite