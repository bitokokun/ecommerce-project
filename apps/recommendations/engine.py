import math
import re
from collections import Counter, defaultdict

CONTENT_WEIGHT = 0.7
COPURCHASE_WEIGHT = 0.3
MIN_SCORE = 0.08

STOPWORDS = {
    "the", "and", "for", "with", "this", "that", "from", "you", "your", "are",
    "was", "has", "have", "can", "all", "any", "its", "our", "not", "but",
    "available", "new", "set", "pack", "high", "quality", "great", "perfect",
}
TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def tokenize(text):
    tokens = []
    for w in TOKEN_RE.findall((text or "").lower()):
        if len(w) < 2 or w in STOPWORDS or w.isdigit():
            continue
        if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        tokens.append(w)
    return tokens


def _product_tokens(p):
    return (
        tokenize(p.get("name")) * 3
        + tokenize(p.get("category")) * 2
        + tokenize(p.get("description"))
    )


def _cosine(a, b):
    if len(a) > len(b):
        a, b = b, a
    return sum(w * b.get(t, 0.0) for t, w in a.items())


class Recommender:
    def __init__(self, products, orders):
        self.names = {p["id"]: p["name"] for p in products}
        self.vectors = self._build_vectors(products)
        self.order_counts, self.pair_counts = self._build_copurchase(orders)

    def _build_vectors(self, products):
        counts = {p["id"]: Counter(_product_tokens(p)) for p in products}
        n_docs = len(products)
        doc_freq = Counter()
        for c in counts.values():
            doc_freq.update(c.keys())
        idf = {t: math.log((1 + n_docs) / (1 + df)) + 1 for t, df in doc_freq.items()}

        vectors = {}
        for pid, c in counts.items():
            vec = {t: (1 + math.log(n)) * idf[t] for t, n in c.items()}
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

    def similar(self, product_id, limit=4):
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
        seeds = {}
        for pid in in_cart:
            if pid in self.vectors:
                seeds[pid] = (0.5, "cart")
        for pid in bought:
            if pid in self.vectors:
                seeds[pid] = (1.0, "bought")
        if not seeds:
            return []

        best = {}
        for cand in self.vectors:
            if cand in seeds:
                continue
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
