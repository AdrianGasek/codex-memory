console.error(
  "Do not publish from the repository root. Publish the CLI package from apps/cli instead.",
);
console.error("Use: cd apps/cli && npm publish --access public");
process.exit(1);
