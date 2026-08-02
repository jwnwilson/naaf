/** A process-unique id for an optimistic (not-yet-persisted) message row. */
export function makeOptimisticId(): string {
  return `optimistic-${crypto.randomUUID()}`;
}
