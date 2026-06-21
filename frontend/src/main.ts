// Wires the pieces together with Google-style dropdown behavior:
//   empty + focused -> Trending searches
//   typing          -> Suggestions from /suggest
//   cleared         -> back to Trending
//   click outside   -> close
// Both lists live in the same dropdown and share keyboard nav.

import { debounce } from "./debounce.js";
import { suggest, search, getTrending } from "./api.js";
import { SuggestionsView } from "./ui.js";
import type { RankMode } from "./api.js";

const input = document.querySelector<HTMLInputElement>("#search")!;
const box = document.querySelector<HTMLElement>("#suggestions")!;
const button = document.querySelector<HTMLButtonElement>("#search-btn")!;
const result = document.querySelector<HTMLElement>("#result")!;
const enhancedToggle = document.querySelector<HTMLInputElement>("#enhanced-toggle")!;

// Basic (all-time) unless the user ticks the recency-aware toggle.
function currentMode(): RankMode {
  return enhancedToggle.checked ? "enhanced" : "basic";
}

// Committing a row (click or Enter) fills the box and submits it.
const view = new SuggestionsView(box, (query) => {
  input.value = query;
  view.clear();
  submit(query);
});

// One sequence number guards BOTH async paths (trending and suggestions). Each
// fired request grabs the next number; a response only renders if it is still
// the latest. So a slow suggestion landing after the box was cleared, or a
// trending fetch landing after the user typed, is dropped instead of painting
// stale content.
let latestSeq = 0;

const runSuggest = debounce(async (prefix: string) => {
  // The input may have changed during the 200ms debounce wait (e.g. cleared to
  // empty). If it no longer matches this prefix, drop the call so it cannot
  // clobber the trending dropdown or show suggestions for a prefix you left.
  if (input.value.trim() !== prefix) return;
  const seq = ++latestSeq;
  view.showLoading();
  try {
    const items = await suggest(prefix, currentMode());
    if (seq !== latestSeq) return;
    view.showResults(items);
  } catch {
    if (seq !== latestSeq) return;
    view.showError("Could not load suggestions");
  }
}, 200);

async function showTrending(): Promise<void> {
  const seq = ++latestSeq;
  try {
    const items = await getTrending(10);
    if (seq !== latestSeq) return;
    if (input.value.trim() !== "") return; // user started typing meanwhile
    view.showTrending(items);
  } catch {
    if (seq !== latestSeq) return;
    view.clear();
  }
}

// The core rule: empty box -> trending, non-empty -> suggestions. Used by both
// focus and input events so they behave identically.
function openForCurrentInput(): void {
  const prefix = input.value.trim();
  if (!prefix) {
    showTrending();
  } else {
    runSuggest(prefix);
  }
}

// Focusing the box (re)opens the right list. Typing keeps it in sync.
input.addEventListener("focus", openForCurrentInput);
input.addEventListener("input", openForCurrentInput);

// Keyboard nav works for whichever list is open.
input.addEventListener("keydown", (e) => {
  switch (e.key) {
    case "ArrowDown":
      e.preventDefault();
      view.moveDown();
      break;
    case "ArrowUp":
      e.preventDefault();
      view.moveUp();
      break;
    case "Enter": {
      // Highlighted row wins; otherwise submit the typed text.
      const highlighted = view.selectActive();
      const query = highlighted ?? input.value;
      if (highlighted) input.value = highlighted;
      submit(query);
      break;
    }
    case "Escape":
      view.clear();
      break;
  }
});

// Flipping the ranking mode re-runs the current query (only meaningful while
// typing; trending is unaffected).
enhancedToggle.addEventListener("change", () => {
  const prefix = input.value.trim();
  if (prefix) runSuggest(prefix);
});

// The Search button submits whatever is currently typed.
button.addEventListener("click", () => submit(input.value));

// The write path: record the query, show the reply, close the dropdown.
async function submit(raw: string): Promise<void> {
  const query = raw.trim();
  if (!query) return;
  view.clear();
  result.textContent = "Searching...";
  try {
    const res = await search(query);
    result.textContent = `${res.message}: "${query}"`;
  } catch {
    result.textContent = "Search failed";
  }
}

// Clicking outside the search area closes the dropdown.
document.addEventListener("click", (e) => {
  if (!input.contains(e.target as Node) && !box.contains(e.target as Node)) {
    view.clear();
  }
});
