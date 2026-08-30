import re

# ---------------------------------------------------------------------------
# Basic helpers (kept for backward compatibility with ranking/tests).
# ---------------------------------------------------------------------------

def normalize_text(text: str) -> str:
    """
    Clean product title for comparison
    """
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_model_number(text: str):
    """
    Extract model numbers like:
    iPhone 15
    Samsung S23
    """
    match = re.search(r"\b\d{1,3}\b", text)
    return match.group() if match else None


def extract_storage(text: str):
    """
    Extract storage values like:
    128GB
    256GB
    1TB
    """
    match = re.search(r"(\d+)\s?(gb|tb)", text.lower())

    if match:
        return match.group(1) + match.group(2)

    return None


# ---------------------------------------------------------------------------
# Brand detection.
# ---------------------------------------------------------------------------

# Brand aliases mapped to a canonical brand token.
BRAND_ALIASES = {
    "iphone": "apple",
    "apple": "apple",
    "samsung": "samsung",
    "galaxy": "samsung",
    "oneplus": "oneplus",
    "xiaomi": "xiaomi",
    "redmi": "xiaomi",
    "poco": "xiaomi",
    "realme": "realme",
    "oppo": "oppo",
    "vivo": "vivo",
    "iqoo": "iqoo",
    "pixel": "google",
    "google": "google",
    "motorola": "motorola",
    "moto": "motorola",
    "nothing": "nothing",
    "asus": "asus",
    "sony": "sony",
    "nokia": "nokia",
    "lenovo": "lenovo",
    "huawei": "huawei",
    "honor": "honor",
    "tecno": "tecno",
    "infinix": "infinix",
    "itel": "itel",
    "lava": "lava",
    "micromax": "micromax",
}

_BRAND_TOKEN = {
    alias: canonical
    for alias, canonical in BRAND_ALIASES.items()
    if re.fullmatch(r"[a-z0-9]+", alias)
}


# ---------------------------------------------------------------------------
# Processor / chipset detection.
# ---------------------------------------------------------------------------

_PROCESSOR_ALIASES = [
    ("snapdragon", ["snapdragon", "qualcomm"]),
    ("exynos", ["exynos"]),
    ("dimensity", ["dimensity", "dimension"]),
    ("tensor", ["tensor"]),
    ("bionic", ["bionic"]),
    ("helios", ["helios"]),
    ("kirin", ["kirin"]),
    ("mediatek", ["mediatek", "media tek", "media tec"]),
]


# ---------------------------------------------------------------------------
# Colour detection.
# ---------------------------------------------------------------------------

_COLOR_PHRASES = [
    # multi-word colours first (longest-match preferred)
    "amber yellow", "onyx black", "cobalt violet", "marble gray", "marble grey",
    "celestial blue", "asphalt black", "titanium gray", "titanium grey",
    "titanium black", "graphite black", "phantom black", "phantom silver",
    "phantom violet", "phantom navy", "midnight black", "midnight blue",
    "starry black", "starry white", "polar white", "platinum silver",
    "ice blue", "sky blue", "ocean blue", "aqua blue", "glacier blue",
    "mint green", "sage green", "forest green", "emerald green", "rose gold",
    "space black", "mystic black", "mystic bronze", "mystic blue",
    "cosmic black", "cosmic blue", "carbon black", "solar black", "solar red",
    "arctic blue", "arctic white", "coral blue", "coral red", "light gray",
    "light grey", "pearl white", "pearl blue", "graphite gray", "silver white",
    "black gold", "navy blue", "steel blue", "royal blue", "baby blue",
    "aqua green", "olive green", "crimson red", "wine red", "sunset orange",
    "caramel brown", "mocha brown", "champagne gold", "ivory white",
    "cream white", "off white", "pure white", "pure black", "jet black",
    "matte black", "multicolor", "multi colour",
    # single-word colours
    "black", "white", "blue", "silver", "gray", "grey", "violet", "purple",
    "gold", "green", "red", "yellow", "pink", "navy", "teal", "bronze",
    "coral", "beige", "brown", "orange", "indigo", "lavender", "magenta",
    "maroon", "olive", "pearl", "cream", "lilac", "mint", "sage", "sky",
    "ocean", "ice", "rose", "crimson", "aqua", "titanium", "graphite",
    "midnight", "phantom", "starry", "cosmic", "mystic", "onyx", "amber",
    "marble", "asphalt", "cobalt", "celestial", "glacier", "polar",
    "platinum", "space", "champagne", "mocha", "matte",
]

_PROCESSOR_TOKENS = {term for _, terms in _PROCESSOR_ALIASES for term in terms}
_COLOR_TOKENS = set(_COLOR_PHRASES)


# Words that clearly mark the end of the model/variant identity block.
_MODEL_STOP_WORDS = (
    _PROCESSOR_TOKENS
    | _COLOR_TOKENS
    | {
        "gb", "tb", "ram", "storage", "memory", "rom", "ssd", "colour", "color",
        "smartphone", "smartphones", "phone", "mobile", "processor", "cpu",
        "chipset", "camera", "cameras", "display", "screen", "inch", "inches",
        "battery", "mah", "watt", "charger", "card", "expandable", "zoom",
        "android", "ios", "cellular",
    }
)

# Noise tokens that may appear inside the identity block but do not identify
# the model (connectivity markers, function words, generic filler).
_MODEL_SKIP_WORDS = {
    "4g", "5g", "dual", "sim", "with", "and", "or", "for", "in", "of", "the",
    "a", "an", "to", "smart", "new", "latest", "ai", "wifi", "bluetooth",
    "nfc",
}


# ---------------------------------------------------------------------------
# Structured variant-attribute extraction.
# ---------------------------------------------------------------------------

def _tokenize_lower(text: str):
    # Keep a '+' as its own token so model spellings like "S24+" are
    # canonicalised to "s24-plus" instead of silently collapsing to "s24".
    text = re.sub(r"\+", " plus ", text.lower())
    return re.findall(r"[a-z0-9]+", text)


def _extract_color(tokens, joined):
    for phrase in sorted(_COLOR_PHRASES, key=lambda p: -len(p.split())):
        if re.search(rf"\b{re.escape(phrase)}\b", joined):
            return phrase
    return None


def _extract_sizes(joined):
    """All size values (GB normalized) found in the title."""
    out = []
    for value, unit in re.findall(r"(\d+(?:\.\d+)?)\s*(gb|tb)", joined):
        gb = float(value) * (1024 if unit == "tb" else 1)
        out.append(gb)
    return out


def _resolve_memory(joined):
    """
    Resolve (ram, storage) size codes from a title.

    - An explicit "X GB RAM" label pins the RAM value.
    - Otherwise, when two sizes are present and one is a RAM-size (<=24GB)
      while the other is a storage size (>=64GB), pair them.
    - A single size <=24GB is treated as RAM, >=32GB as storage.
    Returns ("8gb"|None, "128gb"|None).
    """
    sizes = [gb for gb in _extract_sizes(joined)]

    def canon(gb):
        return f"{int(round(gb))}gb"

    if not sizes:
        return None, None

    ram_match = re.search(r"(\d+(?:\.\d+)?)\s*(gb|tb)\s*ram", joined)
    if ram_match:
        ram_gb = float(ram_match.group(1)) * (1024 if ram_match.group(2) == "tb" else 1)
        rest = [gb for gb in sizes if abs(gb - ram_gb) > 0.001]
        storage = max(rest) if rest else None
        return canon(ram_gb), (canon(storage) if storage else None)

    if len(sizes) >= 2:
        small = min(sizes)
        large = max(sizes)
        if small <= 24 and large >= 64:
            return canon(small), canon(large)
        return None, canon(large)

    (only,) = sizes
    if only <= 24:
        return canon(only), None
    return None, canon(only)


_SIZE_TOKEN = re.compile(r"\d+(?:\.\d+)?(?:gb|tb)$")


def _extract_model_tokens(tokens):
    """Model fingerprint: brand-aware run of identity words vs attributes."""
    brand_idx = None
    i = 0
    n = len(tokens)
    while i < n and tokens[i] in _BRAND_TOKEN:
        brand_idx = i
        i += 1

    start = brand_idx + 1 if brand_idx is not None else 0

    parts = []
    i = start
    n = len(tokens)
    while i < n:
        token = tokens[i]
        nxt = tokens[i + 1] if i + 1 < n else None

        # A brand word re-mentioned after the leading brand run (e.g. the
        # marketing tail "... | Galaxy AI" or "... for Galaxy Processor")
        # must not pollute the model fingerprint.
        if token in _BRAND_TOKEN:
            i += 1
            continue
        if token in _MODEL_STOP_WORDS or _SIZE_TOKEN.match(token):
            break
        if nxt in ("gb", "tb"):
            break
        if token in _MODEL_SKIP_WORDS:
            i += 1
            continue

        parts.append(token)
        i += 1
        if len(parts) >= 4:
            break

    return "-".join(parts) if parts else None


def extract_variant_attributes(text):
    """
    Parse a product title into its variant-defining attributes.

    Returns a dict with keys: brand, model, ram, storage, processor,
    color, edition, model_no.  `None` means the attribute was not
    mentioned in the title (and therefore must not force a split).
    """
    empty = {
        "brand": None,
        "model": None,
        "ram": None,
        "storage": None,
        "processor": None,
        "color": None,
        "edition": None,
        "model_no": None,
    }
    if not text:
        return empty

    joined = " ".join(_tokenize_lower(text))
    tokens = joined.split()

    brand = None
    for token in tokens:
        if token in _BRAND_TOKEN:
            brand = _BRAND_TOKEN[token]

    attrs = dict(empty)
    attrs["brand"] = brand
    attrs["model"] = _extract_model_tokens(tokens)
    attrs["ram"], attrs["storage"] = _resolve_memory(joined)
    attrs["processor"] = _extract_processor(joined)
    attrs["color"] = _extract_color(tokens, joined)
    attrs["edition"] = _extract_edition(joined)
    attrs["model_no"] = _extract_model_no(joined)
    return attrs


def _extract_processor(joined):
    for canonical, terms in _PROCESSOR_ALIASES:
        if any(re.search(rf"\b{re.escape(term)}\b", joined) for term in terms):
            return canonical
    return None


def _extract_edition(joined):
    if re.search(r"\brefurbished\b", joined):
        return "refurbished"
    if re.search(r"\brenew(ed|al)?\b", joined):
        return "renewed"
    if re.search(r"\bopen[- ]box\b", joined):
        return "open-box"
    return None


def extract_model_number_sm(joined):
    m = re.search(r"\bsm-[a-z0-9]{2,}\b", joined)
    return m.group(0) if m else None


def _extract_model_no(joined):
    return extract_model_number_sm(joined)


# ---------------------------------------------------------------------------
# Public product-key / info API.
# ---------------------------------------------------------------------------

def extract_product_info(text):
    """
    Detect brand / model / storage hints in a product title.

    Works across brands. Returns (brand, model, storage) where any
    element may be None.  The model includes qualifiers (FE / Ultra /
    Pro / Max ...) and storage is the real storage size (RAM sizes are
    no longer mistaken for storage).
    """
    attrs = extract_variant_attributes(text)
    return attrs["brand"], attrs["model"], attrs["storage"]


def generate_product_key(title):
    """
    Build a grouping key for any product title.

    Branded products: "<brand>[-<model>][-<storage>]"
      e.g. "apple-15-128gb", "samsung-s24-ultra-256gb".
    Unbranded products: fallback key from the first significant title words,
      so generic items still group instead of being dropped.
    Returns None only for empty/blank titles.
    """
    attrs = extract_variant_attributes(title)
    brand = attrs["brand"]
    model = attrs["model"]
    storage = attrs["storage"]

    parts = []
    if brand:
        parts.append(brand)
        if model:
            parts.append(model)
        if storage:
            parts.append(storage)
        return "-".join(parts)

    words = normalize_text(title).split()
    return "-".join(words[:6]) if words else None