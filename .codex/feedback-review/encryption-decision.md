# Encryption Decision

Date: 2026-04-30

## Decision

Codex-Mem will move the local SQLite encryption feature to application-level field encryption using the Python `cryptography` package. Text fields that carry memory content, history snapshots, audit titles, and injection trace entries will be encrypted before they are written to SQLite and decrypted only at the storage boundary.

SQLCipher is not the selected target for this repository because it changes the SQLite runtime dependency and is harder to install consistently in local Codex plugin environments. Field encryption keeps the current SQLite deployment model while replacing the legacy custom XOR stream with a standard authenticated encryption library.

## Threat Model

This feature is intended to protect memory content if the SQLite database file is copied from disk while the encryption key is unavailable to the attacker.

It does not protect against a compromised running process, malicious code with access to environment variables, API clients that are allowed to read memory through Codex-Mem, plaintext exported files, terminal scrollback, logs created outside Codex-Mem, or secrets that are captured before redaction rules run.

## Key Delivery

The initial production path uses `CODEX_MEM_DB_ENCRYPTION_KEY` from the environment. The key must be supplied by the operator and must not be stored in repository files. Future adapters may read the same logical key from an OS secret store or an operator-managed key file, but repository defaults remain keyless.

## Failure Behavior

When database encryption is enabled and no key is provided, startup diagnostics must report an error or warning and the encrypted storage path must not silently downgrade to plaintext.

When a wrong key is provided, encrypted fields must fail authentication and return a clear decryption error rather than corrupted plaintext.

When ciphertext is malformed or damaged, reads must fail safely with a clear error value or exception that does not expose partial plaintext.

Key rotation will be an explicit migration flow: open the database with the old key, decrypt protected fields, re-encrypt them with the new key, and write a backup before replacing stored values.

## Current Status

As of this decision, the implementation still contains the legacy custom XOR stream. Until the implementation task replaces it, the existing checkbox in the main roadmap means only "local DB content hiding option exists"; it must not be described as production-grade encryption at rest.
