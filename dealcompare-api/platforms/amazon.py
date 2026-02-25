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
                    title_el = product.query_selector("h2")
                    link_el = product.query_selector("h2 a")

                    if not title_el or not link_el:
                        print("Missing title or link — skipping")
                        continue

                    title = title_el.inner_text().strip()
                    href = link_el.get_attribute("href")

                    if not href:
                        print("Missing href — skipping")
                        continue

                    product_url = "https://www.amazon.in" + href

                    price_el = product.query_selector("span.a-price-whole")
                    if price_el:
                        price_text = price_el.inner_text().replace(",", "").strip()
                        price_value = float(price_text)
                        price_display = f"₹{price_text}"
                    else:
                        price_value = 0
                        price_display = "Check price"

                    image_el = product.query_selector("img.s-image")
                    image = image_el.get_attribute("src") if image_el else ""

                    results.append({
                        "title": title,
                        "price_value": price_value,
                        "price_display": price_display,
                        "platform": "Amazon",
                        "url": product_url,
                        "rating": None,
                        "image": image
                    })

                except Exception as e:
                    print("Error inside loop:", e)
                    continue

                if len(results) >= 8:
                    break

            browser.close()

        print("Amazon returned:", len(results))
        return results

    except Exception as e:
        print("Amazon scraping error:", e)
        return []