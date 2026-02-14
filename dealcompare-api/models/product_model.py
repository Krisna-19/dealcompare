from dataclasses import dataclass, asdict

@dataclass
class Product:
    title: str
    platform: str
    price_value: float
    price_display: str
    rating: float | None
    url: str
    image: str
    category: str

    def to_dict(self):
        return asdict(self)
