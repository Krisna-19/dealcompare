from typing import Optional
from pydantic import BaseModel

class Product(BaseModel):
    title: str
    price_value: float
    price_display: str
    platform: str
    url: str
    rating: Optional[float] = None
    image: Optional[str] = ""

