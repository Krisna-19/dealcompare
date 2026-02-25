from playwright.sync_api import sync_playwright
from urllib.parse import quote_plus


def search_amazon(query: str):

    encoded_query = quote_plus(query)
    url = f"https://www.amazon.in/s?k={encoded_query}"

    results = []

    try:
        with sync_playwright() as p:

            browser = p.chromium.launch(headless=False)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
            )
            page = context.new_page()

            print("Opening Amazon URL:", url)

            page.goto(url, timeout=60000)
            page.wait_for_selector('div[data-component-type="s-search-result"]', timeout=20000)

            print("Page loaded")

            products = page.query_selector_all('div[data-component-type="s-search-result"]')

            print("Valid product containers:", len(products))

            for product in products:

                try:
                    # TITLE
                    title = product.query_selector("h2").inner_text().strip()

                    # LINK
                    link = product.query_selector("h2 a").get_attribute("href")
                    product_url = "https://www.amazon.in" + link if link else None

                    if not title or not product_url:
                        continue

                    # PRICE
                    price_element = product.query_selector("span.a-price-whole")
                    if price_element:
                        price_text = price_element.inner_text().replace(",", "").strip()
                        price_value = float(price_text)
                        price_display = f"₹{price_text}"
                    else:
                        price_value = 0
                        price_display = "Check price"

                    # IMAGE
                    image_element = product.query_selector("img.s-image")
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

                except:
                    continue

                if len(results) >= 8:
                    break

            browser.close()

        print("Amazon returned:", len(results))
        return results

    except Exception as e:
        print("Amazon scraping error:", e)
        return []