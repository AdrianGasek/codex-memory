export function parseOptions(args: string[]): Map<string, string[]> {
  const options = new Map<string, string[]>();
  let current: string | null = null;

  for (const arg of args) {
    if (arg.startsWith("--")) {
      current = arg.slice(2);
      if (!options.has(current)) {
        options.set(current, []);
      }
      continue;
    }

    if (current) {
      options.get(current)?.push(arg);
    } else {
      const values = options.get("_") ?? [];
      values.push(arg);
      options.set("_", values);
    }
  }

  return options;
}

export function option(options: Map<string, string[]>, name: string, fallback = ""): string {
  return options.get(name)?.join(" ").trim() || fallback;
}

export function optionList(options: Map<string, string[]>, name: string): string[] {
  return (options.get(name) ?? [])
    .flatMap((value) => value.split(","))
    .map((value) => value.trim())
    .filter(Boolean);
}
