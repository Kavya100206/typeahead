// Wait until calls stop for `delayMs`, then run the function once with the
// latest arguments. Typing "iphone" fast fires one call, not six.
//
// Generic over the argument tuple A, so it works for any function shape and
// keeps full type safety at the call site.
export function debounce<A extends unknown[]>(
  fn: (...args: A) => void,
  delayMs: number,
): (...args: A) => void {
  let timer: number | undefined;

  return (...args: A) => {
    // A newer keystroke arrived before the timer fired: cancel the old one.
    if (timer !== undefined) {
      clearTimeout(timer);
    }
    timer = window.setTimeout(() => fn(...args), delayMs);
  };
}
