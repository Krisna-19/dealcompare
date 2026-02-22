import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-IN,en;q=0.9"
}


def search_amazon(query: str):
    encoded_query = quote_plus(query)
    url = f"https://www.amazon.in/s?k={encoded_query}"

    try:
        response = requests.get(url, headers=HEADERS, timeout=10)

        print("Status Code:", response.status_code)
        print("HTML length:", len(response.text))

        if response.status_code != 200:
            print("Amazon request failed")
            return []

        soup = BeautifulSoup(response.text, "html.parser")

        results = []

        products = soup.select("div.s-result-item")

        for product in products[:8]:

            title_tag = product.select_one("h2 span")
            price_whole = product.select_one("span.a-price-whole")
            link_tag = product.select_one("h2 a")
            image_tag = product.select_one("img.s-image")

            if not title_tag or not link_tag:
                continue

            title = title_tag.get_text(strip=True)

            if price_whole:
                price_text = price_whole.get_text(strip=True).replace(",", "")
                price_value = float(price_text)
                price_display = f"₹{price_text}"
            else:
                price_value = 0
                price_display = "Check price"

            product_url = "https://www.amazon.in" + link_tag["href"]

            image = image_tag["src"] if image_tag else ""

            results.append({
                "title": title,
                "price_value": price_value,
                "price_display": price_display,
                "platform": "Amazon",
                "url": product_url,
                "rating": None,
                "image": image
            })

        return results

    except Exception as e:
        print("Amazon scraping error:", e)
        return []