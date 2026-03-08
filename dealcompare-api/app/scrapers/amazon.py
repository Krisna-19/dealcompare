from playwright.sync_api import sync_playwright


def search_amazon(query: str):

    results = []

    try:
        with sync_playwright() as p:

            browser = p.chromium.launch(headless=False)

            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
            )

            page = context.new_page()

            # Build search URL
            url = f"https://www.amazon.in/s?k={query.replace(' ', '+')}"
            print("Amazon URL:", url)

            page.goto(url, timeout=60000)

            page.wait_for_timeout(3000)

            page.wait_for_selector(
                'div[data-component-type="s-search-result"]',
                timeout=60000
            )

            products = page.query_selector_all(
                'div[data-component-type="s-search-result"]'
            )

            print("Found Amazon containers:", len(products))

            for product in products:

                try:
                    # -------------------
                    # TITLE
                    # -------------------
                    title_el = (
                        product.query_selector("h2 a span") 
                    )
                    if not title_el:
                        continue

                    title = title_el.inner_text().strip()
                    title_lower = title.lower()

                    print("Amazon product:", title)

                    if len(title.split()) < 3:
                        print("Skipping short title:", title)
                        continue

                    # title_lower = title.lower()

                    # Filter accessories
                    blocked_words = [
                                        "case",
                                        "cover",
                                        "screen guard",
                                        "tempered glass",
                                        "back cover"
                                    ]

                    if any(word in title_lower for word in blocked_words):
                        continue

                    # -------------------
                    # PRODUCT LINK
                    # -------------------
                    link_el = product.query_selector("h2 a")
                    if not link_el:
                        continue

                    href = link_el.get_attribute("href")

                    if not href:
                        continue

                    product_url = "https://www.amazon.in" + href

                    # -------------------
                    # PRICE
                    # -------------------
                    price_el = (
                        product.query_selector("span.a-offscreen") or
                        product.query_selector("span.a-price-whole")
                    )

                    if price_el:
                        price_text = price_el.inner_text().replace("₹", "").replace(",", "").strip()
                        try:
                            price_value = float(price_text)
                            price_display = f"₹{price_text}"
                        except:
                            price_value = 0
                            price_display = "Check price"
                    else:
                        price_value = 0
                        price_display = "Check price"

                    # -------------------
                    # IMAGE
                    # -------------------
                    image_el = product.query_selector("img.s-image")

                    image = ""
                    if image_el:
                        image = image_el.get_attribute("src")

                    # -------------------
                    # ADD RESULT
                    # -------------------
                    results.append({
                        "title": title,
                        "price_value": price_value,
                        "price_display": price_display,
                        "platform": "Amazon",
                        "url": product_url,
                        "rating": None,
                        "image": image
                    })

                except Exception:
                    continue

                # limit results
                if len(results) >= 12:
                    break

            browser.close()

    except Exception as e:
        print("Amazon scraping error:", e)

    return results