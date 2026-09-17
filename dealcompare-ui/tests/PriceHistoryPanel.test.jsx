// Component tests for the Price-history modal (PriceHistoryPanel.jsx).
// The price-history API is always mocked with REAL-shaped snapshot data or an
// honest empty/failure response — no fabricated history ever comes from tests.
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, within, waitFor, fireEvent } from "@testing-library/react";

import PriceHistoryPanel from "../src/components/PriceHistoryPanel.jsx";

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

function card(offers) {
  return {
    title: "Apple iPhone 15 (Black, 128 GB)",
    best_price: offers.length ? offers[0].price_display : "",
    best_platform: offers.length ? offers[0].platform : "",
    best_url: offers.length ? offers[0].url : "",
    image: "",
    offers,
  };
}

function obs(price_value, observed_at) {
  return { price_value, observed_at };
}

function historyOffer(key, platform, observations, overrides = {}) {
  const last = observations[observations.length - 1];
  return {
    product_key: key,
    platform,
    title: `Apple iPhone 15 (Black, 128 GB)`,
    url: `https://example.com/${platform.toLowerCase()}/${key}`,
    image: "",
    current_price: typeof last?.price_value === "number" ? last.price_value : null,
    observations,
    ...overrides,
  };
}

function okJson(payload) {
  return { ok: true, status: 200, json: async () => payload };
}

function mockHistoryBackend(map) {
  const fn = vi.fn(async (url) => {
    const parts = String(url).split("/");
    const key = decodeURIComponent(parts[parts.length - 2]);
    const payload = map[key] ?? { product_key: key, catalog_enabled: true, offers: [] };
    return okJson(payload);
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

const REAL_OBSERVATIONS = [
  obs(64000, 1600000000),
  obs(61000, 1605000000),
  obs(58400, 1610000000),
];

function realCard() {
  return card([offer("Flipkart", 58400), offer("Amazon", 61999)]);
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("PriceHistoryPanel", () => {
  it("shows a loading state while the history request is in flight", () => {
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise(() => {})));
    render(<PriceHistoryPanel card={realCard()} onClose={() => {}} />);

    const status = screen.getByRole("status");
    expect(status).toHaveAttribute("aria-busy", "true");
    expect(screen.getByText("Loading price history…")).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("focuses the close button on open", () => {
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise(() => {})));
    render(<PriceHistoryPanel card={realCard()} onClose={() => {}} />);

    expect(screen.getByRole("button", { name: "Close price history" })).toHaveFocus();
  });

  it("closes on Escape", () => {
    const onClose = vi.fn();
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise(() => {})));
    render(<PriceHistoryPanel card={realCard()} onClose={onClose} />);

    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("closes from the close button and keeps dialog clicks from closing it", () => {
    const onClose = vi.fn();
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise(() => {})));
    render(<PriceHistoryPanel card={realCard()} onClose={onClose} />);

    fireEvent.click(screen.getByRole("dialog"));
    expect(onClose).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Close price history" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("closes when the overlay is clicked", () => {
    const onClose = vi.fn();
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise(() => {})));
    render(<PriceHistoryPanel card={realCard()} onClose={onClose} />);

    fireEvent.click(screen.getByRole("dialog").parentElement);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("locks body scroll while open and restores it on close", () => {
    const onClose = vi.fn();
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise(() => {})));
    const { unmount } = render(<PriceHistoryPanel card={realCard()} onClose={onClose} />);

    expect(document.body.style.overflow).toBe("hidden");

    unmount();
    expect(document.body.style.overflow).toBe("");
  });

  it("renders ONLY real observations: chart, summary tiles and store rows", async () => {
    mockHistoryBackend({
      "app-Flipkart": {
        product_key: "app-Flipkart",
        catalog_enabled: true,
        offers: [historyOffer("app-Flipkart", "Flipkart", REAL_OBSERVATIONS)],
      },
      "app-Amazon": {
        product_key: "app-Amazon",
        catalog_enabled: true,
        offers: [historyOffer("app-Amazon", "Amazon", [obs(62000, 1602000000), obs(61000, 1608000000)])],
      },
    });
    render(<PriceHistoryPanel card={realCard()} onClose={() => {}} />);

    const chart = await screen.findByRole("img", { name: /Price trend for Apple iPhone 15/ });
    expect(chart).toBeInTheDocument();

    const summary = screen.getByRole("list", { name: "Price history summary" });
    expect(within(summary).getByText("\u20b958,400")).toBeInTheDocument();
    expect(within(summary).getByText("\u20b964,000")).toBeInTheDocument();
    expect(within(summary).getByText("5")).toBeInTheDocument();
    expect(within(summary).getByText("observations")).toBeInTheDocument();

    const stores = screen.getByRole("list", { name: "Price history per marketplace" });
    expect(within(stores).getByText("Flipkart")).toBeInTheDocument();
    expect(within(stores).getByText("Amazon")).toBeInTheDocument();
    // Per-store rows only show the marketplace's own recorded range.
    const fkRow = within(stores).getByText("Flipkart").closest(".history-store-row");
    expect(within(fkRow).getByText("\u20b958,400")).toBeInTheDocument();
    expect(within(fkRow).getByText("\u20b964,000")).toBeInTheDocument();

    expect(screen.getByText(/Current lowest price:/)).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it("draws a single observation as a dot, never a fake trend line", async () => {
    mockHistoryBackend({
      "app-Flipkart": {
        product_key: "app-Flipkart",
        catalog_enabled: true,
        offers: [historyOffer("app-Flipkart", "Flipkart", [obs(59900, 1600000000)])],
      },
    });
    const { container } = render(<PriceHistoryPanel card={realCard()} onClose={() => {}} />);

    await waitFor(() =>
      expect(screen.getByRole("img", { name: /Price trend for/ })).toBeInTheDocument()
    );
    expect(container.querySelectorAll(".history-chart-line").length).toBe(0);
    expect(container.querySelectorAll(".history-chart-svg circle").length).toBe(1);
  });

  it("honestly reports when no history has been recorded yet", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(okJson({ product_key: "x", catalog_enabled: true, offers: [] }))
    );
    render(<PriceHistoryPanel card={realCard()} onClose={() => {}} />);

    expect(await screen.findByText("Price history is not available yet.")).toBeInTheDocument();
    expect(screen.queryByRole("img", { name: /Price trend/ })).not.toBeInTheDocument();
    // The current live price is still shown honestly, straight from /search.
    expect(screen.getByText(/Current lowest price:/)).toBeInTheDocument();
    expect(screen.getByText("\u20b958,400")).toBeInTheDocument();
  });

  it("shows an honest error state when the history request fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 500, json: async () => ({}) }));
    render(<PriceHistoryPanel card={realCard()} onClose={() => {}} />);

    expect(await screen.findByText("Price history is unavailable right now")).toBeInTheDocument();
    expect(screen.queryByRole("img", { name: /Price trend/ })).not.toBeInTheDocument();
  });

  it("issues one request per unique product_key (dedupe, no duplicates)", async () => {
    const fn = mockHistoryBackend({
      "app-Flipkart": {
        product_key: "app-Flipkart",
        catalog_enabled: true,
        offers: [historyOffer("app-Flipkart", "Flipkart", REAL_OBSERVATIONS)],
      },
    });
    const dupCard = {
      ...realCard(),
      offers: [
        offer("Flipkart", 58400),
        { ...offer("Flipkart", 58400), product_key: "app-Flipkart" },
        offer("Amazon", 61999),
      ],
    };
    render(<PriceHistoryPanel card={dupCard} onClose={() => {}} />);

    await waitFor(() =>
      expect(screen.getByRole("img", { name: /Price trend for/ })).toBeInTheDocument()
    );
    expect(fn).toHaveBeenCalledTimes(2);
    const keys = fn.mock.calls.map(([url]) => {
      const parts = String(url).split("/");
      return decodeURIComponent(parts[parts.length - 2]);
    });
    expect(keys).toEqual(expect.arrayContaining(["app-Flipkart", "app-Amazon"]));
  });

  it("traps focus inside the dialog (Tab wraps first/last)", async () => {
    mockHistoryBackend({
      "app-Flipkart": {
        product_key: "app-Flipkart",
        catalog_enabled: true,
        offers: [historyOffer("app-Flipkart", "Flipkart", REAL_OBSERVATIONS)],
      },
    });
    render(<PriceHistoryPanel card={realCard()} onClose={() => {}} />);

    await waitFor(() =>
      expect(screen.getByRole("img", { name: /Price trend for/ })).toBeInTheDocument()
    );

    const closeBtn = screen.getByRole("button", { name: "Close price history" });
    const listingLinks = screen.getAllByRole("link", { name: /View this listing on/ });
    expect(listingLinks.length).toBeGreaterThan(0);
    const lastLink = listingLinks[listingLinks.length - 1];

    // Shift+Tab on the first focusable wraps to the last.
    closeBtn.focus();
    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(lastLink).toHaveFocus();

    // Tab on the last focusable wraps to the first.
    fireEvent.keyDown(document, { key: "Tab" });
    expect(closeBtn).toHaveFocus();
  });
});