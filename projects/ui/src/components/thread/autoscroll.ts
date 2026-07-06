export interface ScrollMetrics {
  scrollTop: number;
  scrollHeight: number;
  clientHeight: number;
}

/** True when the scroll position is within `threshold` px of the bottom (or the
 * content doesn't overflow). Used to decide whether to auto-follow new messages. */
export function isNearBottom(el: ScrollMetrics, threshold = 50): boolean {
  return el.scrollHeight - el.scrollTop - el.clientHeight <= threshold;
}
