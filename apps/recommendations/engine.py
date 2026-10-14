"""
Recommendation engine.

Plain Python on purpose: no Django, no numpy, no scikit-learn. That keeps it
easy to read and test, and light enough for a free 512 MB server. The catalog
is small, so there is nothing a heavy library would speed up.

Two signals are blended:

1. CONTENT  (TF-IDF + cosine similarity)
   Each product's text (name, category, description) becomes a vector of word
   weights. A word that appears in few products weighs more ("ergonomic" says
   more than "black"). Two products are similar when their vectors point the
   same way. This works from day one, even with zero sales.

2. CO-PURCHASE  (item-item collaborative filtering)
   If many orders contain both A and B, buyers of A tend to want B.
   strength(A, B) = orders with both / sqrt(orders with A * orders with B)
   This needs sales data, so it adds nothing until orders exist.

   pair_score(a, b) = 0.7 * content + 0.3 * co-purchase

Everything the engine returns carries a short human-readable reason, so the
shop can say WHY something is recommended.
"""
import math
import re
from collections import Counter, defaultdict

CONTENT_WEIGHT = 0.7
COPURCHASE_WEIGHT = 0.3
MIN_SCORE = 0.08  # below this, the "match" is mostly noise, so show nothing

STOPWORDS = {
    "the", "and", "for", "with", "this", "that", "from", "you", "your", "are",
    "was", "has", "have", "can", "all", "any", "its", "our", "not", "but",
    "available", "new", "set", "pack", "high", "quality", "great", "perfect",
}
TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def tokenize(text):
    """Lowercase words, minus stopwords, numbers and simple plurals."""
    tokens = []
    for w in TOKEN_RE.findall((text or "").lower()):
        if len(w) < 2 or w in STOPWORDS or w.isdigit():
            continue
        if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]  # "headphones" -> "headphone"
        tokens.append(w)
    return tokens


def _product_tokens(p):
    # The name says the most about a product, then its category, then the
    # description, so repeat the more important text to give it more weight.
    return (
        tokenize(p.get("name")) * 3
        + tokenize(p.get("category")) * 2
        + tokenize(p.get("description"))
    )


def _cosine(a, b):
    """Dot product of two L2-normalised sparse vectors (dict word -> weight)."""
    if len(a) > len(b):
        a, b = b, a
    return sum(w * b.get(t, 0.0) for t, w in a.items())


class Recommender:
    def __init__(self, products, orders):
        """
        products: list of {"id", "name", "category", "description"}  (active ones)
        orders:   list of lists of product ids, one inner list per order
        """
        self.names = {p["id"]: p["name"] for p in products}
        self.vectors = self._build_vectors(products)
        self.order_counts, self.pair_counts = self._build_copurchase(orders)

    # ---- building the model -------------------------------------------------
    def _build_vectors(self, products):
        counts = {p["id"]: Counter(_product_tokens(p)) for p in products}
        n_docs = len(products)
        doc_freq = Counter()
        for c in counts.values():
            doc_freq.update(c.keys())
        # smooth IDF: rare words weigh more, and a word in every product still > 0
        idf = {t: math.log((1 + n_docs) / (1 + df)) + 1 for t, df in doc_freq.items()}

        vectors = {}
        for pid, c in counts.items():
            vec = {t: (1 + math.log(n)) * idf[t] for t, n in c.items()}  # sublinear tf
            norm = math.sqrt(sum(w * w for w in vec.values()))
            vectors[pid] = {t: w / norm for t, w in vec.items()} if norm else {}
        return vectors

    def _build_copurchase(self, orders):
        order_counts = Counter()
        pair_counts = defaultdict(Counter)
        for order in orders:
            items = sorted({pid for pid in order if pid in self.names})
            order_counts.update(items)
            for i, a in enumerate(items):
                for b in items[i + 1:]:
                    pair_counts[a][b] += 1
                    pair_counts[b][a] += 1
        return order_counts, pair_counts

    # ---- scoring ------------------------------------------------------------
    def content_sim(self, a, b):
        return _cosine(self.vectors.get(a, {}), self.vectors.get(b, {}))

    def copurchase_sim(self, a, b):
        together = self.pair_counts.get(a, {}).get(b, 0)
        if not together:
            return 0.0
        return together / math.sqrt(self.order_counts[a] * self.order_counts[b])

    def pair_score(self, a, b):
        content = self.content_sim(a, b)
        cop = self.copurchase_sim(a, b)
        return CONTENT_WEIGHT * content + COPURCHASE_WEIGHT * cop, content, cop

    # ---- the two questions the shop asks -------------------------------------
    def similar(self, product_id, limit=4):
        """Products related to this one. Returns [(id, score, reason)], best first."""
        if product_id not in self.vectors:
            return []
        found = []
        for other in self.vectors:
            if other == product_id:
                continue
            score, content, cop = self.pair_score(product_id, other)
            if score < MIN_SCORE:
                continue
            bought_together = COPURCHASE_WEIGHT * cop > CONTENT_WEIGHT * content
            reason = "Often bought together" if bought_together else "Similar product"
            found.append((other, round(score, 4), reason))
        found.sort(key=lambda t: (-t[1], t[0]))
        return found[:limit]

    def for_user(self, bought, in_cart=(), limit=4):
        """
        Products for one shopper, from what they bought (full weight) and what
        is in their cart (half weight). Each candidate is scored by its best
        match to any of those, which also gives a truthful reason.
        Returns [] when we know nothing about the shopper.
        """
        seeds = {}
        for pid in in_cart:
            if pid in self.vectors:
                seeds[pid] = (0.5, "cart")
        for pid in bought:
            if pid in self.vectors:
                seeds[pid] = (1.0, "bought")  # a purchase beats a cart entry
        if not seeds:
            return []

        best = {}
        for cand in self.vectors:
            if cand in seeds:
                continue  # don't recommend what they already have
            for seed, (weight, kind) in seeds.items():
                score = weight * self.pair_score(seed, cand)[0]
                if score >= MIN_SCORE and score > best.get(cand, (0,))[0]:
                    name = self.names[seed]
                    reason = (
                        f"Because you bought {name}"
                        if kind == "bought"
                        else f"Goes well with {name} in your cart"
                    )
                    best[cand] = (score, reason)

        ranked = [(pid, round(s, 4), r) for pid, (s, r) in best.items()]
        ranked.sort(key=lambda t: (-t[1], t[0]))
        return ranked[:limit]
