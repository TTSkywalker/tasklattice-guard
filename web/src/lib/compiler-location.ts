export function compilerLocation(error: string) {
  const pathMatch = error.match(/([\w./-]+\.co):(\d+)(?::(\d+))?/);
  if (pathMatch) {
    return {
      path: pathMatch[1],
      line: Number(pathMatch[2]),
      column: Number(pathMatch[3] ?? 1),
    };
  }
  const parserMatch = error.match(/line\s+(\d+),\s*column\s+(\d+)/i);
  return parserMatch
    ? {
        path: "main.co",
        line: Number(parserMatch[1]),
        column: Number(parserMatch[2]),
      }
    : null;
}
