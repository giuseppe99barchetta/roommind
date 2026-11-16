/** Per-key JSON snapshot of a settings payload, as last known to the backend. */
export function snapshotSettings(payload: Record<string, unknown>): Record<string, string> {
  return Object.fromEntries(Object.entries(payload).map(([k, v]) => [k, JSON.stringify(v)]));
}

/**
 * Keys of *payload* whose value differs from *saved*. A page left open must send
 * only what was changed on it, so it does not undo changes made elsewhere.
 */
export function changedSettings<T extends Record<string, unknown>>(
  payload: T,
  saved: Record<string, string>,
): Partial<T> {
  return Object.fromEntries(
    Object.entries(payload).filter(([k, v]) => JSON.stringify(v) !== saved[k]),
  ) as Partial<T>;
}
