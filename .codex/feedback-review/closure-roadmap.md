# Roadmapa domknięcia projektu Codex-Mem

Data utworzenia: 2026-04-30

Źródło: `.codex/feedback-review/functional-review.md`

Cel: doprowadzić projekt z poziomu „funkcjonalnie szeroki MVP/Beta” do pełnego DoD produkcyjnego, w którym roadmapowe deklaracje odpowiadają rzeczywistym gwarancjom bezpieczeństwa, integracji, testów, dokumentacji i utrzymania.

## Globalne Definition of Done

Projekt można uznać za domknięty dopiero, gdy wszystkie poniższe warunki są spełnione:

- [ ] Wszystkie pozycje w tej roadmapie mają status `[x]`.
- [ ] Każda funkcja deklarowana w `.codex/ROADMAP.md` ma albo pełną implementację, albo jawnie obniżony opis w dokumentacji.
- [ ] Nie ma placeholderów opisanych jako pełne integracje.
- [ ] Wszystkie endpointy czytające pliki z dysku mają ograniczony, testowany boundary katalogów.
- [ ] Szyfrowanie lokalnej bazy używa standardowego, sprawdzonego mechanizmu kryptograficznego albo feature jest przemianowany na „light obfuscation” i oznaczony jako nieprodukcyjny.
- [ ] Team/shared memory ma jasno zdefiniowaną izolację, konfigurację i testy dostępu.
- [ ] Web viewer jest utrzymywalny poza dużym stringiem w routerze API.
- [ ] Testy jednostkowe, integracyjne, TypeScript typecheck i smoke script przechodzą lokalnie.
- [ ] Raport końcowy w `.codex/feedback-review/final-acceptance.md` dokumentuje wykonane zmiany, komendy walidacyjne i znane ograniczenia.

Wymagane komendy końcowe:

```powershell
uv run --project apps/api pytest apps/api/tests
bun run typecheck
powershell -ExecutionPolicy Bypass -File infra/scripts/smoke.ps1
```

## 1. Produkcyjne szyfrowanie lokalnej bazy

Problem z review: obecne `encrypted-at-rest` ukrywa plaintext, ale bazuje na własnym XOR stream i nie powinno być traktowane jako produkcyjne szyfrowanie.

### 1.1 Decyzja architektoniczna

- [x] Wybrać docelowy model: SQLCipher albo szyfrowanie pól przez `cryptography`.
- [x] Udokumentować model zagrożeń: co chronimy, przed kim, czego nie chronimy.
- [x] Określić sposób dostarczania klucza: env, plik, OS secret store lub inny mechanizm.
- [x] Określić zachowanie przy braku klucza, złym kluczu i rotacji klucza.
- [x] Dodać decyzję do dokumentacji projektu.

DoD:

- [x] W repo istnieje dokument decyzji lub sekcja README opisująca wybrany wariant.
- [x] Obecny claim „encrypted-at-rest” jest zgodny z faktycznym poziomem bezpieczeństwa.

### 1.2 Implementacja szyfrowania

- [x] Usunąć własny XOR stream z `apps/api/app/storage/sqlite.py`.
- [x] Dodać standardową bibliotekę kryptograficzną lub integrację SQLCipher.
- [x] Szyfrować pola tekstowe pamięci, historię, audit i injection trace.
- [x] Nie szyfrować pól potrzebnych do indeksowania tylko wtedy, gdy jest to świadoma decyzja i jest udokumentowana.
- [x] Zapewnić czytelny błąd przy złym kluczu.
- [x] Zapewnić bezpieczne zachowanie przy uszkodzonym ciphertext.

DoD:

- [x] Surowy SQLite nie zawiera plaintext dla `title`, `context`, `resolution`, `history.snapshot`, `audit.title`, `trace.entries`.
- [x] Odczyt przez API zwraca poprawnie odszyfrowane dane.
- [x] Zły klucz nie zwraca śmieci jako poprawnych danych.

### 1.3 Testy szyfrowania

- [x] Test zapisu i odczytu zaszyfrowanej pamięci.
- [x] Test surowego SQLite bez plaintext.
- [x] Test złego klucza.
- [x] Test braku klucza przy włączonym szyfrowaniu.
- [x] Test uszkodzonego ciphertext.
- [x] Test historii, auditu i injection trace.

DoD:

- [x] Testy są w `apps/api/tests`.
- [x] `uv run --project apps/api pytest apps/api/tests` przechodzi.

## 2. Bezpieczny import Markdown

Problem z review: endpoint `POST /memory/import/markdown` przyjmuje dowolną ścieżkę z filesystemu.

### 2.1 Boundary ścieżek

- [x] Zdefiniować dozwolone katalogi importu, domyślnie repo root i `.codex`.
- [x] Użyć `Path.resolve()` dla ścieżki wejściowej i katalogów bazowych.
- [x] Zablokować path traversal i ścieżki spoza dozwolonych katalogów.
- [x] Zablokować import katalogów zamiast plików.
- [x] Zablokować import plików większych niż ustalony limit.

DoD:

- [x] Endpoint zwraca `403` lub `400` dla ścieżek poza boundary.
- [x] Endpoint importuje tylko pliki `.md` lub jawnie dozwolone rozszerzenia.

### 2.2 Tryb importu spoza repo

- [ ] Dodać config typu `migration.allow_external_paths`.
- [ ] Domyślnie ustawić `false`.
- [ ] Dodać diagnostykę configu dla tej opcji.
- [ ] Wymagać jawnego opt-in dla importu z zewnętrznej ścieżki.

DoD:

- [ ] Import spoza repo nie działa bez opt-in.
- [ ] Import spoza repo działa z opt-in i jest testowany.

### 2.3 Testy migracji

- [ ] Test importu domyślnego `.codex/MEMORY.md`.
- [ ] Test importu wskazanego pliku w repo.
- [ ] Test zablokowania `../secret.md`.
- [ ] Test zablokowania absolutnej ścieżki poza repo.
- [ ] Test limitu rozmiaru.
- [ ] Test niepoprawnego Markdown bez crasha.

DoD:

- [ ] Testy obejmują sukces i odmowę.
- [ ] Komunikaty błędów są pomocne.

## 3. Prawdziwe backendy Chroma i pgvector

Problem z review: `ChromaVectorStore` i `PgVectorStore` są obecnie adapterami lokalnymi, nie realną integracją.

### 3.1 Kontrakt vector store

- [ ] Rozszerzyć interfejs `VectorStore` o metody potrzebne dla backendów zewnętrznych.
- [ ] Zdecydować, gdzie są przechowywane embeddingi: SQLite, Chroma, pgvector lub oba.
- [ ] Dodać obsługę błędów backendu i fallback do local tylko jeśli jest jawnie skonfigurowany.
- [ ] Udokumentować różnicę między `local`, `chroma`, `pgvector`.

DoD:

- [ ] Backend `chroma` nie dziedziczy zachowania local bez realnego klienta.
- [ ] Backend `pgvector` nie dziedziczy zachowania local bez realnego klienta.
- [ ] Nieobsługiwany lub niedostępny backend daje jasny błąd diagnostyczny.

### 3.2 Chroma

- [ ] Dodać klienta Chroma.
- [ ] Dodać konfigurację URL, kolekcji i timeoutów.
- [ ] Dodać zapis embeddingu do Chroma przy store/update.
- [ ] Dodać wyszukiwanie similarity przez Chroma.
- [ ] Dodać obsługę niedostępnej usługi.

DoD:

- [ ] Test kontraktowy z mockowanym klientem Chroma.
- [ ] Test błędu połączenia.
- [ ] Dokumentacja uruchomienia lokalnego Chroma.

### 3.3 pgvector

- [ ] Dodać klienta pgvector lub SQL przez Postgres.
- [ ] Dodać migrację/schema dla tabeli wektorów.
- [ ] Dodać zapis i update embeddingów.
- [ ] Dodać wyszukiwanie similarity.
- [ ] Dodać obsługę braku rozszerzenia pgvector.

DoD:

- [ ] Test kontraktowy z mockowanym klientem pgvector.
- [ ] Test błędu DSN.
- [ ] Dokumentacja uruchomienia lokalnego Postgres + pgvector.

### 3.4 Dokumentacja statusu backendów

- [ ] Jeśli realne backendy nie są implementowane, zmienić roadmapę/README na „adapter placeholders”.
- [ ] Jeśli są implementowane, dodać przykłady configu i komendy smoke.

DoD:

- [ ] README nie obiecuje więcej niż działa.
- [ ] Testy rozróżniają wybór backendu od realnej integracji.

## 4. Team memory backend i uprawnienia

Problem z review: `team/search` to lokalny scope `team`, nie pełny backend zespołowy.

### 4.1 Model team memory

- [ ] Zdefiniować, czy team memory jest lokalnym namespace, zewnętrznym backendem, czy trybem synchronizacji.
- [ ] Zdefiniować tenant/team id.
- [ ] Zdefiniować role: reader, writer, admin.
- [ ] Zdefiniować izolację między projektami i zespołami.
- [ ] Zdefiniować audyt operacji team.

DoD:

- [ ] Dokumentacja jasno mówi, czym jest team backend.
- [ ] Nazwy endpointów i configu nie sugerują nieistniejących gwarancji.

### 4.2 Implementacja izolacji

- [ ] Dodać `team_id` lub równoważny namespace.
- [ ] Dodać walidację dostępu do team scope.
- [ ] Dodać wymóg opt-in dla zapisu do team memory.
- [ ] Oddzielić local scope od team scope na poziomie zapytań i zapisu.
- [ ] Dodać audit log dla operacji team.

DoD:

- [ ] Użytkownik/projekt bez dostępu nie widzi pamięci team.
- [ ] Team search nie miesza wpisów innych teamów.
- [ ] Global scope jest dołączany tylko zgodnie z regułami.

### 4.3 Testy team backendu

- [ ] Test izolacji `team:a` vs `team:b`.
- [ ] Test odmowy bez uprawnień.
- [ ] Test zapisu z uprawnieniami.
- [ ] Test auditu operacji team.
- [ ] Test diagnostyki błędnej konfiguracji team backend.

DoD:

- [ ] Testy przechodzą w CI/smoke.
- [ ] Dokumentacja zawiera przykłady configu.

## 5. Shared memory namespaces

Problem z review: shared namespaces działają jako projekt `shared:<name>`, ale potrzebują pełniejszego kontraktu.

### 5.1 Kontrakt namespace

- [ ] Zdefiniować dozwolony format nazwy namespace.
- [ ] Dodać listowanie dostępnych namespace.
- [ ] Dodać endpoint tworzenia/usuwania namespace albo udokumentować, że powstają przez zapis memory.
- [ ] Dodać opis relacji `local`, `global`, `team`, `shared`.

DoD:

- [ ] Namespace ma jednoznaczne reguły nazewnictwa.
- [ ] Wyszukiwanie w namespace nie dołącza przypadkowo global, chyba że config tak mówi.

### 5.2 Testy namespace

- [ ] Test normalizacji nazwy.
- [ ] Test pustej lub niepoprawnej nazwy.
- [ ] Test izolacji dwóch namespace.
- [ ] Test tag filters w namespace.
- [ ] Test progresywnego disclosure dla namespace.

DoD:

- [ ] Shared namespace ma pełne testy API.

## 6. Web viewer jako utrzymywalny moduł

Problem z review: viewer jest dużym stringiem w `routes/memory.py`.

### 6.1 Refactor struktury

- [ ] Przenieść HTML do `apps/api/app/static/viewer.html` albo `apps/api/app/templates/viewer.html`.
- [ ] Przenieść CSS do osobnego pliku albo jasno utrzymać inline tylko jako świadomy MVP.
- [ ] Przenieść JS do osobnego pliku lub modułu.
- [ ] Zostawić router jako cienką warstwę serwującą pliki.

DoD:

- [ ] `routes/memory.py` nie zawiera dużego bloku HTML.
- [ ] Viewer nadal działa pod `/memory/viewer`.

### 6.2 Funkcjonalność viewera

- [ ] Dodać search z filtrami type/project/tags.
- [ ] Dodać debug ranking panel.
- [ ] Dodać podgląd history/audit dla wybranego wpisu.
- [ ] Dodać health diagnostics w viewerze.
- [ ] Dodać czytelne stany loading/error/empty.

DoD:

- [ ] Viewer pozwala przejrzeć memory stream i search bez ręcznego używania API.
- [ ] UI nie ujawnia sekretów ani no-store wpisów poza regułami API.

### 6.3 Testy viewera

- [ ] Test serwowania HTML.
- [ ] Test obecności referencji do assetów.
- [ ] Test podstawowych endpointów używanych przez viewer.
- [ ] Opcjonalnie test Playwright dla search flow.

DoD:

- [ ] Smoke albo osobny test potwierdza, że viewer nie jest pusty i potrafi pobrać dane.

## 7. Dokumentacja i claim alignment

Problem z review: część checkboxów jest spełniona technicznie, ale nazwy mogą sugerować pełniejszą implementację.

### 7.1 README

- [ ] Dodać sekcję „Current guarantees”.
- [ ] Dodać sekcję „Known limitations”.
- [ ] Opisać realny status encryption, team backend, Chroma/pgvector, shared namespaces.
- [ ] Dodać przykłady konfiguracji dla security/sync/team/vector.

DoD:

- [ ] Nowy użytkownik rozumie, co jest produkcyjne, a co eksperymentalne.

### 7.2 Roadmapa główna

- [ ] Jeśli coś zostaje placeholderem, zmienić opis checkboxa na precyzyjny.
- [ ] Dodać nową sekcję „Production hardening”.
- [ ] Przenieść otwarte elementy z tej roadmapy do `.codex/ROADMAP.md` albo linkować tę roadmapę jako źródło DoD.

DoD:

- [ ] `.codex/ROADMAP.md` nie wygląda jak pełna akceptacja funkcji, które są tylko lokalnym MVP.

### 7.3 Compatibility notes

- [ ] Opisać kompatybilność MCP stdio.
- [ ] Opisać kompatybilność MCP HTTP.
- [ ] Opisać wymagania dla Codex hooks.
- [ ] Opisać tryby degraded/passive/approval/debug.

DoD:

- [ ] Dokumentacja zawiera scenariusze instalacji i diagnozy.

## 8. Security hardening

### 8.1 Import i filesystem

- [ ] Wszystkie endpointy i hooki czytające pliki mają path boundary.
- [ ] Testy obejmują path traversal.
- [ ] Testy obejmują symlink poza repo, jeśli system plików wspiera symlinki w CI.

DoD:

- [ ] Brak dowolnego odczytu pliku przez API bez opt-in.

### 8.2 No-store i redakcja

- [ ] No-store działa dla promptów, odpowiedzi, tool payloadów i runtime logów.
- [ ] Redakcja działa przed zapisem do SQLite, exportów, historii, auditu i traces.
- [ ] Safe failure redaction jest pokryte testem dla każdego pola tekstowego.
- [ ] Dodać testy na false positives dla PII, żeby redakcja nie niszczyła zbyt dużo danych technicznych.

DoD:

- [ ] Sekrety i PII nie trafiają do surowej bazy ani exportów.
- [ ] Redakcja ma akceptowalny poziom precyzji.

### 8.3 Sync/share

- [ ] Wszystkie operacje sync/share wymagają opt-in.
- [ ] Team/shared write wymaga osobnego opt-in.
- [ ] Audit zapisuje kto/co/kiedy dla sync/share.

DoD:

- [ ] Nie ma przypadkowej synchronizacji poza lokalny projekt.

## 9. Observability i diagnostyka

### 9.1 Health diagnostics

- [ ] Health diagnostics sprawdza realny status backendu vector, nie tylko plik configu.
- [ ] Health diagnostics sprawdza team backend.
- [ ] Health diagnostics sprawdza encryption config.
- [ ] Health diagnostics sprawdza migracje/schema.

DoD:

- [ ] Endpoint health pokazuje `ok`, `warning` lub `error` per komponent.
- [ ] Nieudany komponent ma actionable message.

### 9.2 Debug traces

- [ ] Search debug pokazuje komponenty score i semantic score.
- [ ] Injection trace pokazuje trimming/summarization reason.
- [ ] Capture debug log pokazuje powód odrzucenia memory.
- [ ] Debug CLI pokazuje config diagnostics.

DoD:

- [ ] Operator może wyjaśnić, dlaczego wpis został zapisany, odrzucony, wyszukany albo wstrzyknięty.

## 10. Test matrix

### 10.1 API tests

- [ ] Memory lifecycle.
- [ ] Ranking/debug search.
- [ ] Injection and trace.
- [ ] History/audit.
- [ ] Import Markdown.
- [ ] Scope isolation.
- [ ] Security redaction.
- [ ] Encryption.
- [ ] Team/shared.
- [ ] Health diagnostics.

DoD:

- [ ] `uv run --project apps/api pytest apps/api/tests` przechodzi.

### 10.2 CLI tests

- [ ] `remember`.
- [ ] `note` alias.
- [ ] `query`.
- [ ] `get`.
- [ ] `update`.
- [ ] `debug`.
- [ ] Obsługa błędów API.

DoD:

- [ ] CLI ma testy lub smoke script pokrywający podstawowe komendy.

### 10.3 MCP tests

- [ ] `store_memory`.
- [ ] `query_memory`.
- [ ] `get_memory`.
- [ ] `update_memory`.
- [ ] `delete_memory`.
- [ ] `timeline`.
- [ ] `get_observations`.
- [ ] `debug_injection`.
- [ ] HTTP transport.

DoD:

- [ ] Fixtures protokołu są aktualne.
- [ ] Testy MCP przechodzą dla stdio i HTTP albo HTTP jest jawnie smoke-testowane osobno.

### 10.4 Hook tests

- [ ] SessionStart injection.
- [ ] UserPromptSubmit injection.
- [ ] Stop capture.
- [ ] PostToolUse capture.
- [ ] Git diff/commit.
- [ ] PR/review feedback.
- [ ] CI/CD failure.
- [ ] Runtime log.
- [ ] No-store tags and paths.
- [ ] Passive/approval/debug modes.
- [ ] API offline degraded mode.

DoD:

- [ ] Hooki nie zapisują niskowartościowych, prywatnych ani sekretowych danych.

### 10.5 Smoke i release

- [ ] TypeScript typecheck.
- [ ] API tests.
- [ ] Package build.
- [ ] JSON manifest validation.
- [ ] Docker build API.
- [ ] Docker build MCP.
- [ ] Opcjonalnie minimalny HTTP MCP smoke.

DoD:

- [ ] `infra/scripts/smoke.ps1` i `infra/scripts/smoke.sh` przechodzą.

## 11. Release readiness

### 11.1 Wersjonowanie i migracje

- [ ] Podbić schema version po zmianach storage/encryption.
- [ ] Dodać migrację istniejącej bazy.
- [ ] Dodać backup przed migracją.
- [ ] Dodać rollback albo instrukcję odzyskania.

DoD:

- [ ] Stara baza testowa migruje bez utraty danych.

### 11.2 Operacyjność

- [ ] Dokumentacja start/stop API.
- [ ] Dokumentacja konfiguracji pluginu.
- [ ] Dokumentacja troubleshooting.
- [ ] Przykładowe `.env` dla local/dev/team.
- [ ] Health endpoint używany w smoke.

DoD:

- [ ] Nowy użytkownik może uruchomić projekt z README bez wiedzy autora.

### 11.3 Final acceptance

- [ ] Utworzyć `.codex/feedback-review/final-acceptance.md`.
- [ ] Wpisać wszystkie wykonane komendy walidacyjne.
- [ ] Wpisać listę zamkniętych ryzyk z `functional-review.md`.
- [ ] Wpisać ewentualne świadomie zaakceptowane ograniczenia.
- [ ] Potwierdzić brak otwartych checkboxów w tej roadmapie.

DoD:

- [ ] Final acceptance jest kompletnym, audytowalnym raportem końcowym.

## Kolejność rekomendowana

1. P1 Security: szyfrowanie i bezpieczny import Markdown.
2. Claim alignment: poprawić dokumentację, żeby nie obiecywała placeholderów.
3. Real vector backends albo jawne obniżenie claimów.
4. Team/shared hardening.
5. Web viewer refactor.
6. Pełny test matrix i final acceptance.

## Kryterium zamknięcia projektu

Projekt jest domknięty, gdy:

- [ ] Nie ma niezaadresowanych P1/P2 z `functional-review.md`.
- [ ] Wszystkie nowe testy przechodzą.
- [ ] Dokumentacja odpowiada faktycznym gwarancjom.
- [ ] Smoke script przechodzi na czystym checkout.
- [ ] `.codex/feedback-review/final-acceptance.md` potwierdza pełne DoD.
