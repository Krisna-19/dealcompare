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
    # Retailer / marketplace designations that look like model tokens but are
    # not part of the product identity (e.g. Amazon "Samsung Galaxy S24 MC 5G").
    # Skipping them lets the identical product merge with the same model sold
    # on another store without "MC" in its title.
    "mc",
}


# ---------------------------------------------------------------------------
# Product-type detection (non-electronics identity).
# ---------------------------------------------------------------------------
# Many unbranded offers carry no brand and no numeric model, so the SKU
# fingerprint degrades to "<colour> + leading words" (e.g. "Men Casual Black").
# Without a product-type term a wallet and a card holder sharing that
# fingerprint would wrongly merge.  Retrieving the material noun lets the
# aggregator keep materially different products on separate cards while still
# merging a genuinely identical wallet listed twice.
#
# Ordered longest-phrase-first so "card holder" wins over "card" and
# "t-shirt" over "shirt".  Electronics models that happen to mention a noun
# (e.g. "Smartphone") should NOT gain a product type here: it is missing
# (None = unknown) for electronics, which never forces a split.
_PRODUCT_TYPE_TERMS = sorted(
    [
        "card holder", "card-holder", "credit card holder", "visiting card holder",
        "wallet", "bifold wallet", "bi-fold wallet", "trifold wallet", "card wallet",
        "purse", "handbag", "shoulder bag", "tote bag", "sling bag", "backpack",
        "laptop bag", "briefcase", "trolley", "suitcase", "luggage", "duffel",
        "jacket", "winter jacket", "bomber jacket", "leather jacket", "blazer",
        "hoodie", "sweatshirt", "sweater", "pullover", "cardigan", "coat",
        "t-shirt", "tshirt", "tee", "shirt", "kurta", "kurti", "dress", "gown",
        "jeans", "trouser", "trousers", "pants", "shorts", "track pants", "joggers",
        "saree", "salwar", "leggings", "tights", "skirt", "shoes", "shoe", "sneaker",
        "sneakers", "sandal", "sandals", "slippers", "boots", "boot", "loafers",
        "socks", "gloves", "scarf", "muffler", "cap", "hat", "beanie", "belt",
        "sunglasses", "eyeglasses", "spectacles", "umbrella", "bag", "clutch",
        "duffle", "tote", "satchel", "crossbody",
    ],
    key=lambda p: -len(p.split()),
)


def _extract_product_type(joined):
    for term in _PRODUCT_TYPE_TERMS:
        if re.search(rf"\b{re.escape(term)}\b", joined):
            return term.replace("-", " ").lower()
    return None


# ---------------------------------------------------------------------------
# Apparel attribute extraction.
#
# Generic apparel titles ("Men Regular Fit Solid Spread Collar Formal Shirt")
# carry little brand/model structure, so the electronics identity machinery
# (which keys on the first meaningful tokens) collapses genuinely different
# garments into one SKU.  For brand-less items we instead pull the concrete
# descriptors a shirt/shoe/lower-body/outerwear title actually states — fit,
# pattern, collar, sleeve, fabric, style and (conservative) clothing size — and
# use those, together with product_type/color/size/pack, as the identity, so
# two shirts are only grouped when their stated attributes genuinely agree.
# ---------------------------------------------------------------------------

# Apparel product-types that should use descriptor-based identity.
_APPEAREL_TYPES = {
    "shirt", "tshirt", "t-shirt", "tee", "kurta", "kurti", "dress", "gown",
    "jeans", "trouser", "trousers", "pants", "shorts", "track pants", "joggers",
    "saree", "skirt", "leggings", "tights", "shoes", "shoe", "sneaker",
    "sneakers", "sandal", "sandals", "slippers", "boots", "boot", "loafers",
    "socks", "gloves", "scarf", "cap", "hat", "beanie", "belt", "jacket",
    "hoodie", "sweatshirt", "sweater", "pullover", "cardigan", "coat", "blazer",
    "kurta", "tunic",
}

# Ordered longest-phrase-first so "button down" wins over a bare term.
_FIT_TERMS = sorted(
    ["slim fit", "regular fit", "relaxed fit", "tight fit", "loose fit",
     "skinny fit", "tailored fit", "comfort fit", "straight fit", "tapered",
     "oversized", "a-line", "fitted"],
    key=lambda p: -len(p.split()),
)

_PATTERN_TERMS = sorted(
    ["checked", "checkered", "check", "plaid", "striped", "stripes", "printed",
     "print", "floral", "graphic", "embroidered", "solid", "plain", "denim",
     "camo", "camouflage", "tie-dye", "polka", "textured", "woven", "paisley",
     "geometric", "colourblock", "colorblock"],
    key=lambda p: -len(p.split()),
)

_COLLAR_TERMS = sorted(
    ["spread collar", "cutaway collar", "mandarin collar", "band collar",
     "button down collar", "button-down", "pointed collar", "classic collar",
     "polo collar", "oxford collar", "shirt collar", "collar"],
    key=lambda p: -len(p.split()),
)

_SLEEVE_TERMS = sorted(
    ["three quarter sleeve", "three-quarter", "half sleeve", "long sleeve",
     "short sleeve", "full sleeve", "sleeveless", "rolled sleeve"],
    key=lambda p: -len(p.split()),
)

_FABRIC_TERMS = sorted(
    ["cotton", "denim", "linen", "polyester", "lycra", "spandex", "elastane",
     "silk", "rayon", "viscose", "oxford", "poplin", "chambray", "twill",
     "velvet", "wool", "knit", "jersey", "mesh", "corduroy", "pique", "georgette",
     "chiffon", "modal", "fleece", "nylon", "crepe", "muslin"],
    key=lambda p: -len(p.split()),
)

_STYLE_TERMS = sorted(
    ["smart casual", "business casual", "formal", "casual", "party", "sports",
     "sporty", "ethnic", "traditional", "wedding", "office", "festive",
     "active", "athletic", "running", "gym", "daily", "regular"],
    key=lambda p: -len(p.split()),
)

# Conservative whole-token clothing sizes.  Only multi-character sizes plus
# single S/M/L markers are considered; matched only for genuine apparel so a
# stray product letter cannot split unrelated items.
_CLOTHING_SIZE_RE = re.compile(r"\b(?:xxxl|xxl|xl|3xl|s|m|l)\b")


def _first_term(term_list, joined):
    """The first phrase from *term_list* present in *joined* (longest-first)."""
    for phrase in term_list:
        if re.search(rf"\b{re.escape(phrase)}\b", joined):
            return phrase
    return None


def _extract_clothing_size(joined):
    """A clothing size token if one is stated, else None."""
    m = _CLOTHING_SIZE_RE.search(joined)
    return m.group(0).upper() if m else None


def _extract_apparel_attrs(joined):
    """Descriptor attributes for brand-less apparel products."""
    return {
        "fit": _first_term(_FIT_TERMS, joined),
        "pattern": _first_term(_PATTERN_TERMS, joined),
        "collar": _first_term(_COLLAR_TERMS, joined),
        "sleeve": _first_term(_SLEEVE_TERMS, joined),
        "fabric": _first_term(_FABRIC_TERMS, joined),
        "style": _first_term(_STYLE_TERMS, joined),
        "clothing_size": _extract_clothing_size(joined),
    }


# Word tokens that carry no identity signal in an apparel title and must never
# be treated as a descriptor when deciding whether two garments are the same
# product (gender/audience markers, function words, generic marketing filler).
_APPAREL_DESCRIPTOR_SKIP = {
    "men", "man", "boys", "girls", "kids", "women", "woman", "unisex", "male",
    "female", "for", "with", "and", "the", "of", "in", "new", "latest", "wear",
    "shop", "buy", "casuals", "wear",
}


def _extract_apparel_descriptor(tokens, attrs):
    """
    The meaningful leftover descriptor tokens of an apparel title — the words
    that are neither generic filler nor already captured by a structured
    attribute (fit/pattern/collar/sleeve/fabric/style/color/size/type).

    This is what keeps "Men Regular Fit Solid Spread Collar Formal Shirt"
    distinct from "Men Regular Fit Solid Casual Formal Shirt": even though both
    share fit/pattern/style, the second carries the descriptor "casual" that
    the first lacks.  Because only *present* tokens are retained (omitted ones
    add nothing), a retailer that simply spells a title more briefly than
    another still merges to the same descriptor — preserving cross-store
    grouping of genuinely identical garments.
    """
    captured = set()
    for value in attrs.values():
        if isinstance(value, str):
            captured.update(value.split())
    seen = []
    for token in tokens:
        if token in _APPAREL_DESCRIPTOR_SKIP:
            continue
        if len(token) < 4:
            continue
        if token in captured:
            continue
        # Drop pure numeric tokens (model numbers, measurements).
        if token.isdigit():
            continue
        if token not in seen:
            seen.append(token)
    return " ".join(seen) if seen else None


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


def _extract_pack_count(joined):
    """
    The number of units bundled in a multi-pack offer.

    Recognises the common phrasing "Pack/Set/Combo of N" (e.g. "Pack of 6",
    "Set of 12", "Combo of 2").  A single-unit offer carries no pack count
    (None = unknown), so it never forces a split against an offer that also
    omits one; but "Pack of 6" and "Pack of 8" of the same product are
    materially different SKUs and must not share a card.
    """
    m = re.search(r"\b(?:pack|set|combo|pair|pr|multipack|multi[- ]?pack)\s+of\s+(\d+)\b", joined)
    return int(m.group(1)) if m else None


def _extract_physical_size(joined):
    """
    The product's physical dimension where a unit (cm/inch) is stated.

    "Women Cabin Size Trolley Bag 55 cm" versus "65 cm" are the same bag in a
    different size and must not share a card.  Capturing the numeric value
    together with its unit (e.g. "55cm") makes size a first-class identity
    attribute.  A title with no size keeps None (unknown), which never forces
    a split, so size-less and size-stated listings of the *same* size-bearing
    product still group.
    """
    m = re.search(r"(\d+(?:\.\d+)?)\s*(cm|inches?|inch|mm|ft|feet)\b", joined)
    if not m:
        return None
    value = m.group(1)
    unit = m.group(2)
    # Normalise singular/plural and abbreviations to a compact stable key.
    if unit in ("inches", "inch"):
        unit = "in"
    elif unit in ("feet", "ft"):
        unit = "ft"
    return f"{value}{unit}"


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
    color, edition, model_no, product_type, pack_count, size_cm.  `None`
    means the attribute was not mentioned in the title (and therefore must
    not force a split).
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
        "product_type": None,
        "pack_count": None,
        "size_cm": None,
        "fit": None,
        "pattern": None,
        "collar": None,
        "sleeve": None,
        "fabric": None,
        "style": None,
        "clothing_size": None,
        "descriptor": None,
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
    # Quantity and physical size are first-class identity attributes: two
    # offers that differ only in pack count or physical size (e.g. "55cm" vs
    # "65cm") are materially different SKUs.  They are None when the title
    # omits them, so a title that does not state a count/size still merges
    # with one that shares all other attributes.
    attrs["pack_count"] = _extract_pack_count(joined)
    attrs["size_cm"] = _extract_physical_size(joined)
    # Product type is only meaningful for unbranded items; branded electronics
    # (brand is set) must not gain a type so their grouping is unchanged.
    if not brand:
        attrs["product_type"] = _extract_product_type(joined)
    # Apparel identity: brand-less garments must not be held together by the
    # electronics "first meaningful tokens" prefix (which wrongly merges
    # "Men Regular Fit Solid Spread Collar..." with "...Casual...").  For an
    # apparel product type we drop that prefix as the model and instead key on
    # the concrete descriptors stated in the title.  Electronics (brand set or
    # no apparel product type) keep the existing model/RAM/storage/colour
    # identity untouched.
    if not brand and attrs["product_type"] in _APPEAREL_TYPES:
        attrs["model"] = None
        attrs.update(_extract_apparel_attrs(joined))
        # Descriptor is a HARD identity signal: an empty string means "no
        # extra descriptor word", so a shirt that adds a descriptor ("casual")
        # stays distinct from one that does not, while two titles that both
        # omit it (or both carry the same one) still merge.
        attrs["descriptor"] = _extract_apparel_descriptor(tokens, attrs) or ""
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