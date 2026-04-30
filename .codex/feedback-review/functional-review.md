# Review funkcjonalności Codex-Mem względem roadmapy

Data review: 2026-04-30

## Podsumowanie

Projekt jest funkcjonalnie szeroki i większość roadmapy ma realne pokrycie w kodzie oraz testach. Dodałem dodatkowe testy przeglądowe w `apps/api/tests/test_roadmap_review.py`, które sprawdzają:

- brak otwartych checkboxów w `.codex/ROADMAP.md`,
- podstawowy przepływ memory: store -> debug search -> inject -> update -> delete -> audit,
- separację scope `team` i `shared:<namespace>`,
- migrację pamięci z Markdown do SQLite.

Wynik walidacji jest zielony, ale review wykazało kilka ważnych ograniczeń funkcjonalnych i bezpieczeństwa, które warto potraktować jako kolejny backlog.

## Najważniejsze ustalenia

### P1: `encrypted-at-rest` nie jest produkcyjnym szyfrowaniem

Opcja szyfrowania lokalnej bazy ukrywa plaintext w SQLite, ale implementacja używa własnego strumienia XOR opartego o SHA-256 i HMAC, bez standardowej biblioteki kryptograficznej, KDF, rotacji klucza ani jasno zdefiniowanego modelu zagrożeń.

Referencje:

- `apps/api/app/storage/sqlite.py:1088`
- `apps/api/app/storage/sqlite.py:1122`

Ryzyko: roadmapowy claim „encrypted-at-rest option” może sugerować wyższy poziom bezpieczeństwa niż faktycznie zapewnia obecna implementacja.

Rekomendacja: użyć sprawdzonego rozwiązania, np. SQLCipher albo `cryptography` z Fernet/AES-GCM + KDF, i dopisać test złego klucza, rotacji oraz integralności.

### P1: endpoint migracji Markdown przyjmuje dowolną ścieżkę z filesystemu

`POST /memory/import/markdown` pozwala podać arbitralny `path`, po czym backend czyta ten plik i importuje zawartość. Jeśli API byłoby dostępne poza zaufanym lokalnym środowiskiem, to jest to ścieżka do odczytu lokalnych plików.

Referencje:

- `apps/api/app/routes/memory.py:580`
- `apps/api/app/routes/memory.py:582`

Ryzyko: lokalna funkcja migracji może stać się mechanizmem exfiltracji plików, szczególnie że endpoint zwraca zaimportowane wpisy w odpowiedzi.

Rekomendacja: ograniczyć import do repozytorium lub `.codex`, walidować `resolve()` względem dozwolonego katalogu i wymagać jawnej flagi/configu dla importu spoza workspace.

### P2: Chroma/pgvector są adapterami pozornymi

`ChromaVectorStore` i `PgVectorStore` dziedziczą po `LocalVectorStore`; nie ma realnego połączenia z Chroma ani pgvector. Testy potwierdzają wybór backendu, ale nie potwierdzają działania zewnętrznego backendu.

Referencje:

- `apps/api/app/storage/vector.py:28`
- `apps/api/app/storage/vector.py:33`
- `apps/api/app/storage/vector.py:47`

Ryzyko: checkbox „optional pgvector/Chroma backend” jest technicznie odhaczony jako interfejs/placeholder, ale nie jako pełna integracja.

Rekomendacja: rozdzielić roadmapę na „adapter interface” i „real backend integration” albo dopisać faktyczne klienty i testy kontraktowe z mockowanym serwerem.

### P2: team backend jest lokalnym scope, nie backendem zespołowym

Endpoint `team/search` przeszukuje projekt `team` w tej samej lokalnej bazie. To działa jako namespace zespołowy, ale nie jest jeszcze backendem teamowym z izolacją użytkowników, synchronizacją, uprawnieniami czy oddzielnym store.

Referencje:

- `apps/api/app/routes/memory.py:386`
- `apps/api/app/routes/memory.py:395`

Ryzyko: nazwa funkcji może obiecywać więcej niż implementacja. Dla lokalnego MVP jest OK, ale dla pracy zespołowej brakuje granic dostępu.

Rekomendacja: przemianować milestone na „local team namespace” albo dopisać backend kontraktowy z auth/scope isolation.

### P3: lokalny web viewer jest przydatny, ale mocno sprzężony z routerem API

Cały HTML/CSS/JS viewera siedzi jako duży string w `routes/memory.py`. Funkcjonalnie działa i jest testowany, ale utrudnia utrzymanie oraz dalszy rozwój UI.

Referencje:

- `apps/api/app/routes/memory.py:216`

Rekomendacja: przenieść viewer do statycznego pliku lub prostego template, nawet jeśli nadal będzie serwowany przez FastAPI.

## Co działa dobrze

- Core memory lifecycle działa end-to-end: zapis, deduplikacja, search, inject, usage counters, update/delete, historia i audit.
- Retrieval ma realny ranking hybrydowy oraz debug view z komponentami score.
- Stop/PostToolUse hooki mają sensowne filtry: low-value, no-store tags, no-store paths, passive/approval/debug.
- Redakcja sekretów i PII ma testy, w tym testy surowej zawartości SQLite.
- Scope local/global/team/shared ma testy izolacji.
- Smoke script uruchamia TypeScript, build pakietów, testy Pythona i walidację JSON manifestów.

## Dodane testy

Nowy plik:

- `apps/api/tests/test_roadmap_review.py`

Zakres:

- `test_roadmap_review_all_items_are_completed`
- `test_roadmap_review_core_memory_flow`
- `test_roadmap_review_scopes_and_markdown_migration`

## Wyniki walidacji

Uruchomione komendy:

```powershell
uv run --project apps/api pytest apps/api/tests
bun run typecheck
powershell -ExecutionPolicy Bypass -File infra/scripts/smoke.ps1
```

Wyniki:

- API tests: `96 passed`
- TypeScript typecheck: OK
- Smoke checks: OK

## Rekomendowany następny backlog

1. Zastąpić własne szyfrowanie sprawdzoną biblioteką lub jasno obniżyć claim w dokumentacji.
2. Ograniczyć ścieżkę importu Markdown do bezpiecznego katalogu.
3. Doprecyzować status Chroma/pgvector: placeholder vs real backend.
4. Doprecyzować team backend: lokalny namespace vs prawdziwy backend zespołowy.
5. Przenieść web viewer poza router API.

