export function cx(classNames, ...maps) {
  if (!classNames) {
    return "";
  }

  const tokens = classNames.split(/\s+/).filter(Boolean);
  const out = [];

  for (const token of tokens) {
    for (const map of maps) {
      if (map && map[token]) {
        out.push(map[token]);
      }
    }
  }

  return [...new Set(out)].join(" ");
}
