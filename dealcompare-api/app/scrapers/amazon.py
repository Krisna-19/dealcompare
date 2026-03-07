from playwright.sync_api import sync_playwright
from app.services.ranking_service import calculate_match_score

def search_amazon(query: str):

    results = []

    try:
        with sync_playwright() as p:

            browser = p.chromium.launch(headless=True)

            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
            )

            page = context.new_page()

            url = f"https://www.amazon.in/s?k={query.replace(' ', '+')}"
            page.goto(url, timeout=60000)

            page.wait_for_selector(
                'div[data-component-type="s-search-result"]'
            )

            products = page.query_selector_all(
                'div[data-component-type="s-search-result"]'
            )

            for product in products:

                title_el = product.query_selector("h2 a span")
                if not title_el:
                    continue

                title = title_el.inner_text().strip()

                link_el = product.query_selector("a.a-link-normal")
                href = link_el.get_attribute("href")

                price_el = product.query_selector("span.a-price-whole")

                if price_el:
                    price_text = price_el.inner_text().replace(",", "")
                    price_value = float(price_text)
                    price_display = f"₹{price_text}"
                else:
                    price_value = 0
                    price_display = "Check price"

                results.append({
                    "title": title,
                    "price_value": price_value,
                    "price_display": price_display,
                    "platform": "Amazon",
                    "url": "https://www.amazon.in" + href,
                    "rating": None,
                    "image": ""
                })

                if len(results) >= 8:
                    break

            browser.close()

    except Exception as e:
        print("Amazon scraping error:", e)

    return results