from playwright.sync_api import sync_playwright
from urllib.parse import quote_plus


def search_amazon(query: str):
    encoded_query = quote_plus(query)
    url = f"https://www.amazon.in/s?k={encoded_query}"

    results = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()

            page.goto(url, timeout=60000)
            page.wait_for_selector("div.s-result-item", timeout=15000)

            products = page.query_selector_all("div.s-result-item")

            for product in products[:8]:

                title_element = product.query_selector("h2 span")
                price_whole = product.query_selector("span.a-price-whole")
                link_element = product.query_selector("h2 a")
                image_element = product.query_selector("img.s-image")

                if not title_element or not link_element:
                    continue

                title = title_element.inner_text().strip()

                if price_whole:
                    price_text = price_whole.inner_text().replace(",", "").strip()
                    try:
                        price_value = float(price_text)
                        price_display = f"₹{price_text}"
                    except:
                        price_value = 0
                        price_display = "Check price"
                else:
                    price_value = 0
                    price_display = "Check price"

                product_url = "https://www.amazon.in" + link_element.get_attribute("href")
                image = image_element.get_attribute("src") if image_element else ""

                results.append({
                    "title": title,
                    "price_value": price_value,
                    "price_display": price_display,
                    "platform": "Amazon",
                    "url": product_url,
                    "rating": None,
                    "image": image
                })

            browser.close()

        return results

    except Exception as e:
        print("Amazon Playwright scraping error:", e)
        return []