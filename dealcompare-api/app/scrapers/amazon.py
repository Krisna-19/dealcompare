from playwright.async_api import async_playwright
from urllib.parse import quote_plus
from app.services.ranking_service import calculate_match_score


async def search_amazon(query: str):

    encoded_query = quote_plus(query)
    url = f"https://www.amazon.in/s?k={encoded_query}"

    results = []

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
            )
            page = await context.new_page()

            print("Opening Amazon URL:", url)

            page.goto(url, timeout=60000)
            page.wait_for_selector(
                'div[data-component-type="s-search-result"]',
                timeout=20000
            )

            print("Page loaded")

            products = page.query_selector_all(
                'div[data-component-type="s-search-result"]'
            )

            print("Valid product containers:", len(products))

            for product in products:

                try:
                    # -----------------------
                    # TITLE (visible title)
                    # -----------------------
                    title_element = product.query_selector("h2 a span")
                    if not title_element:
                        continue

                    title = title_element.inner_text().strip()
                    # Reject short / invalid titles
                    if len(title.split()) < 2:
                        continue

                    # Must contain model number from query
                    from services.ranking_service import extract_model_number

                    query_model = extract_model_number(query)
                    title_model = extract_model_number(title)

                    if query_model and title_model:
                        if query_model != title_model:
                            continue

                    if not title:
                        continue

                    # -----------------------
                    # MATCH SCORE FILTER
                    # -----------------------
                    from services.ranking_service import strict_model_match

                    # strict model filter first
                    if not strict_model_match(query, title):
                        continue

                    score = calculate_match_score(query, title)

                    if score < 15:
                        continue

                    # -----------------------
                    # PRODUCT LINK
                    # -----------------------
                    link_element = product.query_selector("a.a-link-normal")
                    if not link_element:
                        continue

                    href = link_element.get_attribute("href")
                    if not href or "/dp/" not in href:
                        continue

                    product_url = "https://www.amazon.in" + href

                    # -----------------------
                    # PRICE
                    # -----------------------
                    price_element = product.query_selector("span.a-price-whole")

                    if price_element:
                        price_text = price_element.inner_text().replace(",", "").strip()
                        try:
                            price_value = float(price_text)
                            price_display = f"₹{price_text}"
                        except:
                            price_value = 0
                            price_display = "Check price"
                    else:
                        price_value = 0
                        price_display = "Check price"

                    # -----------------------
                    # IMAGE
                    # -----------------------
                    image_element = product.query_selector("img.s-image")
                    image = image_element.get_attribute("src") if image_element else ""

                    # -----------------------
                    # APPEND RESULT
                    # -----------------------
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
                    print("Loop error:", e)
                    continue

                if len(results) >= 8:
                    break

            browser.close()

        print("Amazon returned:", len(results))
        return results

    except Exception as e:
        print("Amazon scraping error:", e)
        return []