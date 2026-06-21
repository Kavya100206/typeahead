"""Generate a synthetic but realistic query,count dataset.

Two properties we need:
  1. Prefix overlap: many queries share leading characters, so the trie and the
     top-k logic are actually exercised.
  2. Skewed counts: a few very popular queries and a long rare tail (Zipf-like),
     so ranking by count is meaningful.

Run once:  python scripts/generate_dataset.py
Output:    data/queries.csv  (header: query,count)
"""

import csv
import random
from pathlib import Path

random.seed(42)  # reproducible dataset across runs

OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "queries.csv"
TARGET_ROWS = 120_000  # comfortably above the 100k requirement

# Head terms: the popular search stems. Their order roughly is their popularity.
HEADS = [
    "iphone", "ipad", "ipod", "ip address", "java", "javascript", "python",
    "samsung galaxy", "google pixel", "macbook", "windows", "linux", "android",
    "chrome", "firefox", "react", "angular", "vue", "node js", "django",
    "flask", "spring boot", "kubernetes", "docker", "aws", "azure", "github",
    "stack overflow", "leetcode", "coursera", "udemy", "netflix", "amazon",
    "flipkart", "youtube", "instagram", "whatsapp", "telegram", "spotify",
    "tesla", "bitcoin", "ethereum", "nifty", "sensex", "cricket score",
    "world cup", "premier league", "weather", "news", "flights", "hotels",
    "pizza", "biryani", "coffee", "headphones", "laptop", "smart watch",
    "air conditioner", "refrigerator", "washing machine", "running shoes",
    "yoga mat", "protein powder", "data structures", "system design",
    "machine learning", "deep learning", "neural network", "sql tutorial",
    "git commands", "regex", "binary search", "dynamic programming",
    "interview questions", "resume template", "cover letter", "salary",
    "income tax", "mutual funds", "credit card", "home loan", "car insurance",
    "movie tickets", "train ticket", "bus booking", "online shopping",
    "best phone", "gaming laptop", "mechanical keyboard", "wireless mouse",
    "noise cancelling", "power bank", "usb cable", "graphic card",
    "processor", "motherboard", "ram", "ssd", "monitor", "webcam",
    "microphone", "ring light", "tripod", "drone", "action camera",
    "electric scooter", "mountain bike", "treadmill", "dumbbells",
    "face wash", "sunscreen", "shampoo", "perfume", "wrist watch",
    "sunglasses", "backpack", "wallet", "sneakers", "formal shoes",
]

# Modifier words appended to heads to create the long tail.
MODIFIERS = [
    "price", "review", "near me", "online", "buy", "best", "cheap", "offer",
    "discount", "2024", "2025", "pro", "max", "mini", "case", "cover",
    "tutorial", "for beginners", "pdf", "course", "vs samsung", "vs iphone",
    "specifications", "features", "comparison", "alternatives", "free",
    "download", "install", "setup", "error", "not working", "fix", "guide",
    "tips", "tricks", "examples", "cheat sheet", "interview", "jobs",
    "in india", "in usa", "delivery", "warranty", "second hand", "refurbished",
    "color options", "battery life", "camera quality", "display", "weight",
]


def main() -> None:
    base = {}  # query -> count
    n_heads = len(HEADS)

    # Single heads get the highest counts via a Zipf-like 1/rank curve.
    for rank, head in enumerate(HEADS, start=1):
        base[head] = int(1_000_000 / rank)

    # head + modifier, then head + mod + mod2, until we hit the target.
    while len(base) < TARGET_ROWS:
        head = random.choice(HEADS)
        head_pop = base[head]
        if random.random() < 0.45:
            q = f"{head} {random.choice(MODIFIERS)}"
            words = 2
        else:
            m1, m2 = random.sample(MODIFIERS, 2)
            q = f"{head} {m1} {m2}"
            words = 3
        if q in base:
            continue
        # Longer queries are rarer; jitter so ties are uncommon.
        count = max(1, int(head_pop / (12 * words) * random.uniform(0.3, 1.0)))
        base[q] = count

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["query", "count"])
        for query, count in base.items():
            writer.writerow([query, count])

    print(f"wrote {len(base)} rows to {OUT_PATH}")


if __name__ == "__main__":
    main()
