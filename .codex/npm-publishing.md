# npm Publishing

The public npm package is `apps/cli/package.json` with package name `codex-memory`.
Do not publish from the repository root; the root package is private and exists for
workspace development.

## Prepare A Patch Release

1. Confirm npm still points at the previous version:

   ```bash
   npm view codex-memory version dist-tags --json
   ```

2. Bump the same patch version in both files:

   ```text
   package.json
   apps/cli/package.json
   ```

3. Refresh the lockfile:

   ```bash
   bun install
   ```

4. Add a `CHANGELOG.md` entry for the new version.

## Verify The Package

Run these checks from the repository root:

```bash
bun run apps/cli/src/index.ts --version
node infra/scripts/check-publishable-confirmed.mjs apps/cli/package.json
bun run pack:smoke
```

For a fuller release smoke, also run:

```bash
bun run smoke:npx-install
```

The package tarball is written under `dist/release/`, for example:

```text
dist/release/codex-memory-1.0.6.tgz
```

## Publish

Publishing is automated on every push to `main`. The GitHub workflow
`.github/workflows/publish-npm.yml` reads the version from
`apps/cli/package.json`, skips publishing if that exact version already exists
on npm, and publishes only after release checks pass.

The repository must have an npm automation token saved as the GitHub Actions
secret `NPM_TOKEN`.

Manual publishing is still possible when needed. Publish only from the CLI
package directory:

```bash
cd apps/cli
npm pack --dry-run
npm publish --access public --provenance
```

Before confirming publish, check that the dry run includes `package.json`,
`README.md`, `LICENSE`, `dist`, and `runtime`.

After publishing, verify npm:

```bash
npm view codex-memory version dist-tags --json
```
