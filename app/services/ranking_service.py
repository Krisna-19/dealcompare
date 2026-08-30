import re
from rapidfuzz import fuzz
from app.utils.text_utils import normalize_text, extract_product_info, _BRAND_TOKEN


# -----------------------------
# TEXT NORMALIZATION
# -----------------------------
def normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


# -----------------------------
# EXTRACT MODEL NUMBER
# -----------------------------
def extract_model_number(text: str):
    """
    Extracts numbers like:
    15, 14, 13, 17 etc from 'iPhone 15'
    """
    match = re.search(r"\b\d{1,2}\b", text)
    return match.group() if match else None


# -----------------------------
# EXTRACT STORAGE (128GB etc)
# -----------------------------
def extract_storage(text: str):
    match = re.search(r"(\d{2,4})\s?gb", text.lower())
    return match.group(1) if match else None


# -----------------------------
# STRICT MODEL MATCH CHECK
# -----------------------------
def strict_model_match(query: str, title: str) -> int:
    """
    Strict attribute comparison between query and title.

    Returns an int score:
      +20  model numbers both present and equal
      -10  model numbers both present but different
      +20  storage values both present and equal
    A score > 0 means the titles agree on every conflicting attribute.
    """
    score = 0

    query = normalize(query)
    title = normalize(title)

    query_model = extract_model_number(query)
    title_model = extract_model_number(title)

    query_storage = extract_storage(query)
    title_storage = extract_storage(title)

    # MODEL must match if exists
    if query_model and title_model:
        if query_model == title_model:
            score += 20
        else:
            score -= 10

    # STORAGE must match if exists
    if query_storage and title_storage:
        if query_storage == title_storage:
            score += 20

    return score


# -----------------------------
# MATCH SCORE
# -----------------------------
def calculate_match_score(query: str, title: str):

    query_norm = normalize_text(query)
    title_norm = normalize_text(title)

    # Base similarity
    score = fuzz.token_set_ratio(query_norm, title_norm)

    # Extract important tokens
    query_model = extract_model_number(query_norm)
    title_model = extract_model_number(title_norm)

    query_storage = extract_storage(query_norm)
    title_storage = extract_storage(title_norm)

    # Model match bonus
    if query_model and title_model and query_model == title_model:
        score += 20

    # Storage match bonus
    if query_storage and title_storage and query_storage == title_storage:
        score += 20

    return score


# -----------------------------
# RELEVANCE FILTER
# -----------------------------

# Function words / generic filler that are too weak to establish relevance on
# their own.  A title that only shares one of these words with the query
# (e.g. "men", "women", "for", "and") is NOT considered genuinely relevant.
_QUERY_STOPWORDS = {
    "a", "an", "and", "or", "for", "in", "of", "the", "to", "with", "on",
    "by", "at", "from",
    "men", "woman", "man", "women", "boy", "girl", "boys", "girls", "unisex",
    "kids", "child", "children",
    "new", "latest", "smart", "best", "buy", "online", "shop", "shopping",
    "sale", "deal", "price", "card", "gift", "combo", "pack",
}


def _query_is_specific(query):
    """
    True when the query names a concrete product/model/SKU rather than a
    generic category.

    A specific query produces a variant model slug that carries a numeric
    model identifier (e.g. "samsung galaxy s24" -> "s24", "iphone 15" -> "15",
    "oneplus 12" -> "12").  Generic category queries ("tshirt men", "tshirt")
    yield a slug with no such number and must be handled by relevance instead.
    """
    _brand, model, _storage = extract_product_info(query)
    if not model:
        return False
    return any(ch.isdigit() for ch in model)


def _meaningful_query_tokens(query):
    """
    The query tokens strong enough to signal relevance on their own.

    Applies word normalization, drops generic stopwords/filler ("men",
    "women", "for", ...) and very short tokens so that a weak one-word hit
    cannot, by itself, make an unrelated product relevant.
    """
    return [
        t for t in _merged_tokens(query)
        if len(t) >= 3 and t not in _QUERY_STOPWORDS
    ]


def _merged_tokens(text):
    """
    Word tokens with single-letter prefixes joined onto their successor.

    Product titles write "T-Shirt" while users search "tshirt": after plain
    normalization the hyphen becomes a space ("t shirt") and the weak token
    "shirt" would not match the query token "tshirt".  Merging any leading
    single-letter token with the following one turns both "t-shirt" and
    "t shirt" into the same relevant token "tshirt".
    """
    parts = normalize(text).split()
    merged = []
    i = 0
    while i < len(parts):
        token = parts[i]
        if len(token) == 1 and i + 1 < len(parts):
            merged.append(token + parts[i + 1])
            i += 2
        else:
            merged.append(token)
            i += 1
    return merged


# Canonical sub-variant qualifiers that change a base model's identity
# (Ultra / Plus / FE / Pro / Max).  A title that names the queried base model
# AND one of these refers to a different product and must be excluded.  "S24+"
# is normalised to "s24-plus" upstream, and the qualifier appears as the token
# immediately after the base model token inside a slug.
_VARIANT_QUALIFIERS = {"ultra", "plus", "fe", "pro", "max"}


def _model_anchor(model):
    """
    The token inside a model slug that names the concrete base model — the
    part carrying the numeric generation (e.g. "s24" from "s24-ultra",
    "s25" from "s25-fe").  Used to recognise accessories that mention the
    queried model without weakening the generation/series split.
    """
    for token in model.split("-"):
        if any(ch.isdigit() for ch in token):
            return token
    return model


def _variant_of(model):
    """
    The canonical sub-variant qualifier of a model slug, i.e. the token
    immediately following the base model token (or None for the base model).

    Examples: "s24" -> None, "s24-ultra" -> "ultra", "s24-plus" -> "plus",
    "s24-fe" -> "fe", "qrioh-s24-back-case" -> None (base-S24 accessory),
    "case-creation-s24-ultra" -> "ultra" (an S24 Ultra accessory).
    """
    anchor = _model_anchor(model)
    if not anchor:
        return None
    tokens = model.split("-")
    try:
        i = tokens.index(anchor)
    except ValueError:
        return None
    following = tokens[i + 1] if i + 1 < len(tokens) else None
    return following if following in _VARIANT_QUALIFIERS else None


def _model_matches(q_model, t_model):
    """
    Whether *t_model* refers to the same product as *q_model*.

    The query's OWN sub-variant is respected in both directions:
      - same base model anchor is required (S24 vs S25/iPhone/Turbo), AND
      - the same sub-variant is required (base S24 vs Ultra/Plus/FE).
    This keeps base S24 products + genuine base-S24 accessories for an "s24"
    query, and keeps ONLY Ultra (resp. Plus/FE) for an "s24 ultra" (resp.
    plus/fe) query — no base S24 leaking into variant queries and no
    Ultra/Plus/FE leaking into a base S24 query.
    """
    if t_model == q_model:
        return True

    anchor = _model_anchor(q_model)
    if not anchor:
        return False

    if anchor not in t_model.split("-"):
        # Different base model/generation (S25, iPhone 15, Turbo 5, ...).
        return False

    # Same base model: require the same sub-variant (identity, not just base).
    return _variant_of(q_model) == _variant_of(t_model)


def _laptop_accessory_signal(text):
    """True when a title clearly describes a laptop ACCESSORY, not a laptop."""
    return any(
        t in _merged_tokens(text)
        for t in (
            "bag", "backpack", "rucksack", "sleeve", "case", "cover", "pouch",
            "mouse", "keyboard", "monitor", "stand", "charger", "adapter",
            "cable", "dock", "cooling", "skin", "sticker", "guard", "filter",
        )
    )


# ASUS laptop product lines.  A real ASUS laptop may omit the literal word
# "laptop" (e.g. "ASUS Vivobook 15", "ASUS Chromebook"), so these line names
# count as laptop-type signals.
_ASUS_LAPTOP_LINES = {
    "vivobook", "expertbook", "zenbook", "proart", "tuf", "rog", "chromebook",
}


def _is_laptop_device(text):
    """True when a title describes an actual laptop device, not an accessory."""
    tokens = set(_merged_tokens(text))
    if any(t in _laptop_tokens for t in tokens):
        return not _laptop_accessory_signal(text)
    return any(t in tokens for t in _ASUS_LAPTOP_LINES) and not _laptop_accessory_signal(text)


# Words that indicate the product itself is a laptop (a device, not a bag).
_laptop_tokens = {"laptop", "notebook"}


def _query_brand_token(query):
    """The canonical brand token in a query (e.g. 'asus'), or None."""
    for t in _meaningful_query_tokens(query):
        if t in _BRAND_TOKEN:
            return _BRAND_TOKEN[t]
    return None


def _query_has_laptop_type(query):
    """True when the query itself asks for laptop-type products."""
    meaningful = set(_meaningful_query_tokens(query))
    return bool(meaningful & (_laptop_tokens | {"chromebook"}))


def filter_irrelevant_products(products, query):
    """
    Remove products that are clearly off-topic for the given query.

    Two modes, both strict (they only reject, never promote):

    1. Specific product/SKU queries (e.g. "Samsung Galaxy S24"):
       reject any product whose detected variant model slug differs from the
       query's (Galaxy S25 / S24 Ultra / S24 FE / iPhone when searching Galaxy
       S24, ...), while still keeping genuine S24 accessories whose title
       names the queried model (e.g. an "Samsung Galaxy S24 5G Back Case").
       Products with no detectable model are kept (cannot be ruled out).

    2. Generic / category queries (e.g. "tshirt men", "tshirt"):
       reject products that share no meaningful query token with their title.
       This keeps genuinely relevant items (t-shirts for "tshirt men") while
       still dropping clearly unrelated ones (e.g. a refrigerator or a phone),
       instead of the old bug that rejected everything because the full query
       slug never equalled the product title slug.
    """
    # --- Specific product/model query: preserve exact-model matching ---------
    if _query_is_specific(query):
        _q_brand, q_model, _q_storage = extract_product_info(query)

        # Should not happen for a "specific" query, but stay defensive.
        if not q_model:
            return products

        filtered = []
        for product in products:
            title = product.get("title", "")
            _t_brand, t_model, _t_storage = extract_product_info(title)

            # Title with no detectable model: keep — could be an accessory.
            if not t_model:
                filtered.append(product)
                continue

            # Both query and title have a model: keep only if they refer to
            # the same base product (or a genuine accessory for it).
            if not _model_matches(q_model, t_model):
                continue

            filtered.append(product)

        return filtered

    # --- Generic / category query: token relevance ---------------------------
    query_tokens = _meaningful_query_tokens(query)
    # Nothing meaningful to judge by (e.g. "men" alone) — cannot rule out.
    if not query_tokens:
        return products

    # Brand + laptop-type query ("laptop asus" / "asus laptop"): only that
    # brand's actual laptop devices qualify — never bags, backpacks, sleeves,
    # mouse/keyboard/monitor, or other accessories, and never other brands.
    q_brand = _query_brand_token(query)
    brand_typed = bool(q_brand and _query_has_laptop_type(query))

    title_norms = [
        (product, set(_merged_tokens(product.get("title", ""))))
        for product in products
    ]

    relevant = []
    for product, title_words in title_norms:
        if brand_typed:
            if q_brand not in title_words:
                continue
            if not _is_laptop_device(product.get("title", "")):
                continue
            relevant.append(product)
        elif any(t in title_words for t in query_tokens):
            relevant.append(product)

    return relevant
