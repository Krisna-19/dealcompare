// Component-level tests for the comparison results experience (Home.jsx +
// ProductCard + SearchHeader + FeedbackState).  The network layer is always
// mocked — no real marketplace requests are ever made from tests.
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import Home from "../src/pages/Home.jsx";

const API_BASE = "http://127.0.0.1:8000";

function offer(platform, price_value, overrides = {}) {
  return {
    title: "Apple iPhone 15 (Black, 128 GB)",
    product_key: `app-${platform}`,
    platform,
    price_value,
    price_display: `\u20b9${price_value.toLocaleString("en-IN")}`,
    url: `https://example.com/${platform.toLowerCase()}/${price_value}`,
    image: "",
    ...overrides,
  };
}

function card(offers, overrides = {}) {
  const best = offers.reduce((a, b) => (a.price_value <= b.price_value ? a : b));
  return {
    title: "Apple iPhone 15 (Black, 128 GB)",
    best_price: best.price_display,
    best_platform: best.platform,
    best_url: best.url,
    image: offers[0].image || "",
    offers,
    ...overrides,
  };
}

function okResponse(payload) {
  return { ok: true, status: 200, json: async () => payload };
}

function mockFetchOnce(payload) {
  const fn = vi.fn().mockResolvedValue(okResponse(payload));
  vi.stubGlobal("fetch", fn);
  return fn;
}

function searchOkPayload(cards) {
  return { message: "Products compared successfully", category: "Electronics", results: cards };
}

async function search(user, query, payload) {
  mockFetchOnce(payload);
  await user.type(screen.getByLabelText("Search products"), query);
  await user.click(screen.getByRole("button", { name: /^Compare/ }));
  await waitFor(() => expect(screen.getByRole("button", { name: /^Compare/ })).toBeEnabled());
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Home results experience", () => {
  it("renders an initial guidance state with suggestions and NO products", () => {
    render(<Home />);
    expect(screen.getByText("Compare live prices across marketplaces")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Search for iPhone 15" })).toBeInTheDocument();
    expect(screen.queryByRole("article")).not.toBeInTheDocument();
  });

  it("renders a real offer: title, price, platform and a safe View Deal link", async () => {
    const user = userEvent.setup();
    const flipkart = offer("Flipkart", 59900, { image: "https://img.example/fk.jpg" });
    render(<Home />);

    await search(user, "iphone 15", searchOkPayload([card([flipkart])]));

    const article = await screen.findByRole("article");
    expect(within(article).getByText("Apple iPhone 15 (Black, 128 GB)")).toBeInTheDocument();
    expect(within(article).getByText("\u20b959,900", { selector: ".price" })).toBeInTheDocument();
    expect(within(article).getByText("\u20b959,900", { selector: ".best-headline-price" })).toBeInTheDocument();
    expect(within(article).getByText("Flipkart")).toBeInTheDocument();

    const link = within(article).getByRole("link", { name: /View deal on Flipkart/ });
    expect(link).toHaveAttribute("href", flipkart.url);
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");

    const img = within(article).getByRole("img");
    expect(img).toHaveAttribute("src", flipkart.image);
    expect(img).toHaveAttribute("alt", "Apple iPhone 15 (Black, 128 GB)");
    // The /search URL came from the existing VITE-or-default base.
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining(`${API_BASE}/search?query=${encodeURIComponent("iphone 15")}`),
      expect.anything()
    );
  });

  it("with one marketplace returning data, shows ONLY that marketplace", async () => {
    const user = userEvent.setup();
    render(<Home />);

    await search(user, "samsung", searchOkPayload([card([offer("Flipkart", 55999)])]));

    const article = await screen.findByRole("article");
    expect(within(article).getByText("Flipkart")).toBeInTheDocument();
    expect(within(article).queryByText("Amazon")).not.toBeInTheDocument();
    expect(within(article).queryByText("Myntra")).not.toBeInTheDocument();
    expect(within(article).queryByText("Ajio")).not.toBeInTheDocument();
  });

  it("highlights exactly one offer as the best price (lowest valid) in a multi-offer card", async () => {
    const user = userEvent.setup();
    const flipkart = offer("Flipkart", 59900);
    const amazon = offer("Amazon", 61999);
    render(<Home />);

    await search(user, "iphone 15", searchOkPayload([card([flipkart, amazon])]));

    const article = await screen.findByRole("article");
    // Headline label confirms an overall winner was computed.
    expect(within(article).getByText("Best price", { selector: ".best-headline-label" })).toBeInTheDocument();
    // Exactly ONE offer row is flagged as the best price.
    expect(within(article).getAllByText("Best price", { selector: ".best-chip" }).length).toBe(1);

    const bestRow = within(article).getByText(flipkart.price_display, { selector: ".price" }).closest(".offer-row");
    expect(bestRow).not.toBeNull();
    expect(bestRow.classList.contains("offer-row-best")).toBe(true);
    expect(within(bestRow).getByText("Best price", { selector: ".best-chip" })).toBeInTheDocument();

    const otherRow = within(article).getByText(amazon.price_display, { selector: ".price" }).closest(".offer-row");
    expect(otherRow.classList.contains("offer-row-best")).toBe(false);
    expect(within(otherRow).queryByText("Best price", { selector: ".best-chip" })).not.toBeInTheDocument();
  });

  it("shows MRP + savings only when the backend supplies a valid original price", async () => {
    const user = userEvent.setup();
    const withMrp = offer("Flipkart", 59900, { mrp: 79900 });
    const noMrp = offer("Amazon", 61999);
    render(<Home />);

    await search(user, "iphone 15", searchOkPayload([card([withMrp, noMrp])]));

    const article = await screen.findByRole("article");
    // MRP row: strikethrough original price + savings badge (25%).
    expect(within(article).getByText("\u20b979,900")).toBeInTheDocument();
    expect(within(article).getByText("Save \u20b920,000 (25%)")).toBeInTheDocument();

    // The other offer has no MRP -> no invented strikethrough / savings.
    const nonMrpBadges = within(article).queryAllByText(/^Save /);
    expect(nonMrpBadges.length).toBe(1);
  });

  it("falls back to a placeholder when no image is supplied", async () => {
    const user = userEvent.setup();
    render(<Home />);

    await search(user, "iphone 15", searchOkPayload([card([offer("Flipkart", 59900)])]));

    const article = await screen.findByRole("article");
    expect(within(article).queryByRole("img")).not.toBeInTheDocument();
    expect(within(article).getByText("No image")).toBeInTheDocument();
  });

  it("honestly reports empty results (no fake products or offers)", async () => {
    const user = userEvent.setup();
    render(<Home />);

    await search(user, "zxqjkl", { message: "No products found", category: "General", results: [] });

    expect(await screen.findByText("No products found")).toBeInTheDocument();
    expect(screen.queryByRole("article")).not.toBeInTheDocument();
    expect(screen.queryByText(/View Deal/i)).not.toBeInTheDocument();
  });

  it("shows the error state when the API request fails", async () => {
    const user = userEvent.setup();
    const failingFetch = vi
      .fn()
      .mockRejectedValueOnce(new Error("conn refused"))
      .mockRejectedValueOnce(new Error("conn refused"));
    vi.stubGlobal("fetch", failingFetch);

    render(<Home />);
    await user.type(screen.getByLabelText("Search products"), "iphone");
    await user.click(screen.getByRole("button", { name: /^Compare/ }));

    expect(await screen.findByText("Couldn’t compare prices")).toBeInTheDocument();
    expect(failingFetch).toHaveBeenCalledTimes(2); // one warm-up retry
  });

  it("shows the error state on an HTTP error response", async () => {
    const user = userEvent.setup();
    const fn = vi.fn().mockResolvedValue({ ok: false, status: 500, json: async () => ({}) });
    vi.stubGlobal("fetch", fn);

    render(<Home />);
    await user.type(screen.getByLabelText("Search products"), "iphone");
    await user.click(screen.getByRole("button", { name: /^Compare/ }));

    expect(await screen.findByText("Couldn’t compare prices")).toBeInTheDocument();
  });

  it("shows a loading skeleton while the search is in flight", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise(() => {})));

    render(<Home />);
    await user.type(screen.getByLabelText("Search products"), "iphone");
    await user.click(screen.getByRole("button", { name: /^Compare/ }));

    const status = screen.getByRole("status", { name: /Searching deals/i });
    expect(status).toHaveAttribute("aria-busy", "true");
    expect(screen.getByRole("button", { name: /^Searching/ })).toBeDisabled();
  });

  it("renders the no-valid-offers sub-state for a card whose offers are unusable", async () => {
    const user = userEvent.setup();
    const bogus = { ...offer("Flipkart", 0), price_value: 0, url: "" };
    render(<Home />);

    await search(user, "iphone 15", searchOkPayload([card([bogus])]));

    const article = await screen.findByRole("article");
    expect(within(article).getByText(/No valid offers available/)).toBeInTheDocument();
    expect(within(article).queryByText(/View Deal/i)).not.toBeInTheDocument();
  });

  it("filters offers by store without hiding the card when it still has offers", async () => {
    const user = userEvent.setup();
    const flipkart = offer("Flipkart", 59900);
    const amazon = offer("Amazon", 61999);
    render(<Home />);

    await search(user, "iphone 15", searchOkPayload([card([flipkart, amazon])]));

    await screen.findByRole("article");

    await user.click(screen.getByRole("button", { name: "Amazon" }));

    const article = screen.getByRole("article");
    expect(within(article).getByText("Amazon")).toBeInTheDocument();
    expect(within(article).queryByText(flipkart.price_display)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Amazon" })).toHaveAttribute("aria-pressed", "true");
  });
});