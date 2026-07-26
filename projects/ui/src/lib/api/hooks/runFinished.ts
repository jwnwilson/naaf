/** True iff the event list contains a terminal `run_finished` event. */
export function hasRunFinished(events: { type: string }[]): boolean {
  return events.some((ev) => ev.type === "run_finished");
}
