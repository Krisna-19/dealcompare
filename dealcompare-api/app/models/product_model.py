from typing import Optional

class Product:
    def __init__(
        self,
        title: str,
        platform: str,
        price_value: float,
        price_display: str,
        url: str,
        rating: Optional[float] = None,
        image: Optional[str] = ""
    ):
        self.title = title
        self.platform = platform
        self.price_value = price_value
        self.price_display = price_display
        self.url = url
        self.rating = rating
        self.image = image
