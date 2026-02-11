from dataclasses import dataclass

@dataclass
class Product:
    title: str
    platform: str
    price_display: str
    price_value: float
    rating: float | None
    image: str
    url: str
    category: str
    score: float
