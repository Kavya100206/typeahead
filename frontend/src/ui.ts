// Owns the dropdown DOM and its state. The same dropdown shows two kinds of
// list: typeahead suggestions (while typing) and trending searches (while the
// box is empty and focused). Both are plain rows, so one keyboard-nav and one
// selection path serve both. Knows nothing about fetch or debounce; main.ts
// drives it.

import type { Suggestion, TrendingItem } from "./api.js";

// Called when the user commits a row (Enter, or a click).
export type SelectHandler = (query: string) => void;

// One rendered row. `meta` is the right-aligned text (a count for suggestions,
// empty for trending). Keyboard nav and selection only need `query`.
interface Row {
  query: string;
  meta: string;
}

export class SuggestionsView {
  private box: HTMLElement;
  private rows: Row[] = [];
  private header: string | null = null; // e.g. "Trending searches"
  private activeIndex = -1; // keyboard-highlighted row; -1 = none
  private onSelect: SelectHandler;

  constructor(box: HTMLElement, onSelect: SelectHandler) {
    this.box = box;
    this.onSelect = onSelect;
  }

  // --- States ---------------------------------------------------------------

  showLoading(): void {
    this.reset();
    this.box.innerHTML = `<div class="status">Loading...</div>`;
    this.open();
  }

  showError(message: string): void {
    this.reset();
    this.box.innerHTML = `<div class="status status-error">${escapeHtml(message)}</div>`;
    this.open();
  }

  showResults(items: Suggestion[]): void {
    this.reset();
    this.rows = items.map((s) => ({ query: s.query, meta: s.count.toLocaleString() }));
    if (this.rows.length === 0) {
      this.box.innerHTML = `<div class="status">No suggestions</div>`;
      this.open();
      return;
    }
    this.render();
  }

  showTrending(items: TrendingItem[]): void {
    this.reset();
    this.header = "Trending searches";
    this.rows = items.map((t) => ({ query: t.query, meta: "" }));
    if (this.rows.length === 0) {
      this.box.innerHTML =
        `<div class="dropdown-header">Trending searches</div>` +
        `<div class="status">No trending searches yet</div>`;
      this.open();
      return;
    }
    this.render();
  }

  // Hide the dropdown and forget everything.
  clear(): void {
    this.reset();
    this.box.innerHTML = "";
    this.box.classList.remove("open");
  }

  // --- Keyboard navigation (shared by both lists) ---------------------------

  moveDown(): void {
    if (this.rows.length === 0) return;
    this.activeIndex = (this.activeIndex + 1) % this.rows.length;
    this.render();
  }

  moveUp(): void {
    if (this.rows.length === 0) return;
    this.activeIndex =
      (this.activeIndex - 1 + this.rows.length) % this.rows.length;
    this.render();
  }

  selectActive(): string | null {
    if (this.activeIndex < 0) return null;
    return this.rows[this.activeIndex].query;
  }

  // --- Internals ------------------------------------------------------------

  private reset(): void {
    this.rows = [];
    this.header = null;
    this.activeIndex = -1;
  }

  private render(): void {
    const headerHtml = this.header
      ? `<div class="dropdown-header">${escapeHtml(this.header)}</div>`
      : "";
    const rowsHtml = this.rows
      .map((row, i) => {
        const active = i === this.activeIndex ? " active" : "";
        const metaHtml = row.meta
          ? `<span class="count">${escapeHtml(row.meta)}</span>`
          : "";
        return (
          `<li class="row${active}" data-index="${i}">` +
          `<span class="query">${escapeHtml(row.query)}</span>${metaHtml}</li>`
        );
      })
      .join("");
    this.box.innerHTML = headerHtml + `<ul class="list">${rowsHtml}</ul>`;

    // Mouse selects the same way the keyboard does. mousedown (not click) so it
    // fires before the input loses focus.
    this.box.querySelectorAll<HTMLElement>(".row").forEach((el) => {
      el.addEventListener("mousedown", (e) => {
        e.preventDefault();
        const index = Number(el.dataset.index);
        this.onSelect(this.rows[index].query);
      });
    });
    this.open();
  }

  private open(): void {
    this.box.classList.add("open");
  }
}

// User-entered data gets escaped before injection as HTML, so a query like
// "<img onerror=...>" cannot run as markup.
function escapeHtml(text: string): string {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}
