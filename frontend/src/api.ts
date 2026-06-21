// The single place that knows where the backend lives and what it returns.
// Everything else imports typed functions from here and never touches fetch.

const BASE_URL = "http://localhost:8000";

// Mirrors one item in the backend's /suggest response. `score` is present only
// in enhanced (recency-aware) mode.
export interface Suggestion {
  query: string;
  count: number;
  score?: number;
}

export type RankMode = "basic" | "enhanced";

// The full shape of GET /suggest. Kept private; callers only need Suggestion[].
interface SuggestResponse {
  prefix: string;
  suggestions: Suggestion[];
}

// Ask the backend for completions of `prefix`. `mode` picks all-time (basic) or
// recency-aware (enhanced) ranking. Throws on a non-2xx so the caller can show
// the error state.
export async function suggest(
  prefix: string,
  mode: RankMode = "basic",
): Promise<Suggestion[]> {
  const url = `${BASE_URL}/suggest?q=${encodeURIComponent(prefix)}&mode=${mode}`;
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`suggest failed: ${res.status}`);
  }
  const data: SuggestResponse = await res.json();
  return data.suggestions;
}

// One trending query and its decayed recency score.
export interface TrendingItem {
  query: string;
  score: number;
}

interface TrendingResponse {
  trending: TrendingItem[];
}

// Fetch the current trending queries (by recency score, hottest first).
export async function getTrending(k = 10): Promise<TrendingItem[]> {
  const res = await fetch(`${BASE_URL}/trending?k=${k}`);
  if (!res.ok) {
    throw new Error(`trending failed: ${res.status}`);
  }
  const data: TrendingResponse = await res.json();
  return data.trending;
}

// The shape of POST /search's reply. Phase 3 just returns a dummy message.
interface SearchResponse {
  message: string;
}

// Submit a search. This is the write path: the backend records the query and
// bumps its count. Returns the dummy confirmation message.
export async function search(query: string): Promise<SearchResponse> {
  const res = await fetch(`${BASE_URL}/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  });
  if (!res.ok) {
    throw new Error(`search failed: ${res.status}`);
  }
  return res.json();
}
