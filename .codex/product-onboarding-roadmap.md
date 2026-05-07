# Roadmapa: productowy onboarding Codex-Memory

Data utworzenia: 2026-05-06

Cel: zmienić Codex-Memory z narzędzia wymagającego developerskiego składania usług w normalne narzędzie developerskie instalowane jednym flow, z zachowaniem obecnego trybu dev-toolkit dla contributorów i zaawansowanych użytkowników.

Benchmark UX: claude-mem oferuje `npx claude-mem install` oraz marketplace/plugin flow, a README podkreśla automatyczną konfigurację hooków, workera i zależności: https://github.com/thedotmack/claude-mem

## Definition of Done

- [x] Nowy użytkownik może uruchomić w repo jedną komendę: `npx codex-mem install`.
- [x] Instalator działa z założeniem minimum: Node.js + npm; Bun i uv są wykrywane albo bootstrapowane przez instalator.
- [x] Po instalacji działa API pamięci, MCP, hooki Codex i podstawowe komendy CLI bez ręcznego `bun install`, `uv sync` i ręcznego startu `uvicorn`.
- [x] Instalator tworzy bezpieczną domyślną konfigurację lokalną, ale nie zapisuje sekretów do repo.
- [x] Użytkownik ma komendy: `codex-mem status`, `doctor`, `start`, `stop`, `restart`, `uninstall`, `upgrade`.
- [x] Obecny onboarding developerski zostaje utrzymany jako osobna ścieżka `Developer Toolkit`.
- [x] README zaczyna się od produkcyjnego Quick Start, a ręczne komendy są przeniesione do sekcji development/contributing.
- [x] Smoke test na czystym repo potwierdza instalację, health check, zapis pamięci, query, MCP tools i hook degraded/active mode.
- [x] Testy API, CLI, MCP, installer dry-run i typecheck przechodzą lokalnie.
- [x] Jeśli `codex-mem` w npm nie jest pod kontrolą projektu, release jest blokowany; na potrzeby tej roadmapy zakładamy ownership pakietu `codex-mem`.

## Publiczny kontrakt v1

- [x] `npx codex-mem install` jest głównym happy path.
- [x] `codex-mem install --yes` działa bez interakcji dla CI/smoke.
- [x] `codex-mem install --dev-toolkit` zachowuje obecne repo-local workflow i wypisuje komendy developerskie.
- [x] `codex-mem doctor` pokazuje status Node/npm, Bun, uv, API, DB, MCP, plugin config, hooks i portów.
- [x] `codex-mem status/start/stop/restart` zarządza lokalnym workerem przez PID file i logi w user cache, nie jako systemowy service w v1.
- [x] `codex-mem uninstall` usuwa konfigurację pluginu/hooków z bieżącego repo, ale domyślnie nie usuwa danych pamięci bez `--delete-data`.

## Taski implementacyjne

### 1. Packaging i entrypoint npm

- [x] Przekształcić pakiet CLI w publiczny pakiet `codex-mem` z binarką `codex-mem`.
- [x] Upewnić się, że paczka npm zawiera zbudowany CLI, MCP server, plugin assets, hook runner oraz źródła/artefakty potrzebne do uruchomienia API.
- [x] Dodać release check blokujący publikację, jeśli `package.json` nadal ma `private: true` w publikowanym pakiecie.
- [x] Dodać `npm pack` smoke, który instaluje paczkę z lokalnego tarballa i uruchamia `codex-mem --version`.

### 2. Instalator produkcyjny

- [x] Dodać komendę `install`, która wykrywa repo root, tworzy `.codex/mem.config.json` i konfiguruje domyślny lokalny storage.
- [x] Dodać bootstrap Bun i uv: jeśli są dostępne, użyć istniejących; jeśli nie, zainstalować/cache'ować w katalogu użytkownika i pokazać jasny błąd przy braku możliwości.
- [x] Utworzyć user runtime directory: Windows `%USERPROFILE%\.codex-mem`, Unix `$HOME/.codex-mem`.
- [x] Instalować runtime API/MCP/plugin do katalogu użytkownika, a w repo zostawiać tylko lekką konfigurację.
- [x] Po instalacji uruchomić worker i wykonać health check `GET /health` oraz `/memory/health/diagnostics`.

### 3. Worker manager

- [x] Dodać `start`, `stop`, `restart`, `status` oparte o PID file, port config i logi w `.codex-mem/logs`.
- [x] Domyślnie startować API na `127.0.0.1:8000`; jeśli port zajęty przez Codex-Memory, użyć istniejącego procesu, a jeśli przez coś innego, wybrać kolejny wolny port i zapisać config.
- [x] MCP stdio ma używać aktualnego `CODEX_MEM_API_URL` z konfiguracji instalatora.
- [x] Dodać odporność na offline API: hooki nie mogą psuć pracy Codexa, tylko raportować degraded mode.

### 4. Plugin i hooki jako produkt

- [x] Zmienić hook commands z repo-relatywnych ścieżek typu `python plugins/.../hook_memory.py` na stabilny entrypoint `codex-mem hook <event>`.
- [x] Instalator ma aktualizować `.agents/plugins/marketplace.json` w bieżącym repo, wskazując na user-level plugin assets.
- [x] Dodać rollback konfiguracji, jeśli instalacja pluginu lub MCP nie przejdzie health checka.
- [x] Dodać `uninstall`, które usuwa wpis pluginu z `.agents/plugins/marketplace.json` i zostawia backup poprzedniej wersji pliku.

### 5. Developer Toolkit zostaje

- [x] README ma rozdzielić ścieżki: `Quick Start` dla użytkownika i `Developer Toolkit` dla contributorów.
- [x] Zachować obecne skrypty: `bun install`, `uv sync`, `api:dev`, `mcp:dev`, `cli:test`, `api:test`.
- [x] Dodać `codex-mem dev doctor`, które sprawdza lokalny checkout i obecne monorepo scripts.
- [x] Upewnić się, że zmiany instalatora nie łamią repo-local plugin scaffold.

### 6. Dokumentacja i UX

- [x] Przepisać początek README na flow: `npx codex-mem install`, `codex-mem status`, `codex-mem remember ...`, `codex-mem query ...`.
- [x] Dodać sekcję "What gets installed" prostym językiem: API, SQLite, MCP, hooks, plugin config.
- [x] Dodać sekcję "Privacy and local data" z informacją, gdzie są dane i jak je usunąć.
- [x] Dodać troubleshooting dla Windows PowerShell, zajętego portu, braku npm, braku uprawnień i offline API.
- [x] Dodać porównanie ścieżek: product install vs developer toolkit.

### 7. Testy i akceptacja

- [x] Dodać unit tests dla parsera komend install/start/stop/status/doctor/uninstall.
- [x] Dodać installer dry-run tests dla Windows i Unix pathów.
- [x] Dodać smoke test na temp repo: `npx --package <local-tarball> codex-mem install --yes`.
- [x] Smoke ma potwierdzić: config utworzony, worker działa, `remember/query` działa, MCP tools list działa, plugin manifest jest poprawny.
- [x] Dodać test migracji z istniejącego dev-toolkit checkoutu do product install bez utraty danych SQLite.
- [x] Wymagane komendy końcowe: `bun run typecheck`, `bun run cli:test`, `uv run --project apps/api pytest apps/api/tests`, `powershell -ExecutionPolicy Bypass -File infra/scripts/smoke.ps1`, `codex-mem doctor`.

## Założenia

- [x] Zakładamy ownership pakietu npm `codex-mem`; jeśli ownership nie jest potwierdzony, release nie może zostać oznaczony jako gotowy.
- [x] V1 używa user-level managed process, nie natywnego Windows service/systemd.
- [x] V1 jest lokalny-first: sync/team remote nie jest wymagany do produkcyjnego onboardingu.
- [x] Dev-toolkit nie jest usuwany; zmieniamy domyślną ścieżkę użytkownika, nie architekturę contributorów.
