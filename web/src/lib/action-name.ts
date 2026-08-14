const PRODUCT_PREFIX = "TaskLattice";
const ACTION_SUFFIX = "Action";

/**
 * Keep the stable runtime identifier intact while presenting a compact code label.
 */
export function compactActionName(name: string) {
  let compact = name;
  if (compact.startsWith(PRODUCT_PREFIX)) compact = compact.slice(PRODUCT_PREFIX.length);
  if (compact.endsWith(ACTION_SUFFIX)) compact = compact.slice(0, -ACTION_SUFFIX.length);
  return compact || name;
}
