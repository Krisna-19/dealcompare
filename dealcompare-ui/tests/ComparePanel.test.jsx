// Component tests for the "Compare offers" modal (ComparePanel.jsx).
// Data is always mocked /search payloads — never real network requests.
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, within, fireEvent } from "@testing-library/react";

import ComparePanel from "../src/components/ComparePanel.jsx";

function offer(platform, price_value, overrides = {}) {
  const display =
    typeof price_value === "number" && Number.isFinite(price_value) && price_value > 0
      ? `\u20b9${price_value.toLocaleString("en-IN")}`
      : "";
  return {
    title: "Apple iPhone 15 (Black, 128 GB)",
    product_key: `app-${platform}`,
    platform,
    price_value,
    price_display: display,
    url: `https://example.com/${platform.toLowerCase()}/${price_value ?? "x"}`,
    image: "",
    ...overrides,
  };
}

function bestOf(offers) {
  const valid = offers.filter(
    (o) => typeof o.price_value === "number" && o.price_value > 0
  );
  return valid.reduce(
    (best, o) => (best == null || o.price_value < best.price_value ? o : best),
    null
  );
}

function card(offers, overrides = {}) {
  const best = bestOf(offers);
  return {
    title: "Apple iPhone 15 (Black, 128 GB)",
    best_price: best ? best.price_display : "",
    best_platform: best ? best.platform : "",
    best_url: best ? best.url : "",
    image: (offers.find((o) => o.image) || {}).image || "",
    offers,
    ...overrides,
  };
}

function rowPlatforms(container) {
  return Array.from(container.querySelectorAll(".compare-row .platform-name")).map(
    (n) => n.textContent
  );
}

function rowPrices(container) {
  return Array.from(container.querySelectorAll(".compare-row .compare-price")).map(
    (n) => n.textContent
  );
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ComparePanel", () => {
  it("renders every valid offer and excludes invalid offers", () => {
    const offers = [
      offer("Flipkart", 59900, { image: "https://img.example/fk.jpg" }),
      offer("Amazon", 61999),
      offer("Myntra", 0, { title: "Broken Myntra listing" }),
      offer("Ajio", null),
    ];
    const { container } = render(<ComparePanel card={card(offers)} onClose={() => {}} />);

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Apple iPhone 15 (Black, 128 GB)" })).toBeInTheDocument();
    expect(rowPlatforms(container)).toEqual(["Flipkart", "Amazon"]);
    expect(screen.queryByText("Myntra")).not.toBeInTheDocument();
  });

  it("marks exactly one offer as the best price (lowest valid)", () => {
    const offers = [
      offer("Flipkart", 59900),
      offer("Amazon", 61999),
      offer("Myntra", 58999),
    ];
    const { container } = render(<ComparePanel card={card(offers)} onClose={() => {}} />);

    const bestChips = screen.getAllByText("Best price", { selector: ".best-chip" });
    expect(bestChips.length).toBe(1);

    const rows = container.querySelectorAll(".compare-row");
    const bestRow = Array.from(rows).find((row) =>
      within(row).getByText("\u20b958,999")
    );
    expect(bestRow).toBeDefined();
    expect(bestRow.classList.contains("compare-row-best")).toBe(true);
  });

  it("resolves price ties to a single best-price offer deterministically", () => {
    const offers = [
      offer("Amazon", 59900),
      offer("Flipkart", 59900),
      offer("Myntra", 65000),
    ];
    render(<ComparePanel card={card(offers)} onClose={() => {}} />);
    expect(screen.getAllByText("Best price", { selector: ".best-chip" }).length).toBe(1);
  });

  it("shows only the true price difference for non-best offers", () => {
    const offers = [
      offer("Flipkart", 55999),
      offer("Amazon", 57499),
    ];
    const { container } = render(<ComparePanel card={card(offers)} onClose={() => {}} />);

    expect(screen.getByText("+\u20b91,500 more than best")).toBeInTheDocument();
    const rows = container.querySelectorAll(".compare-row");
    // The best row must not advertise a difference.
    expect(within(rows[0]).queryByText(/more than best/)).not.toBeInTheDocument();
  });

  it("never invents savings when the backend supplies no MRP", () => {
    render(
      <ComparePanel
        card={card([offer("Flipkart", 59900), offer("Amazon", 61999)])}
        onClose={() => {}}
      />
    );
    expect(screen.queryByText(/^Save /)).not.toBeInTheDocument();
    expect(screen.queryByText("\u20b979,900")).not.toBeInTheDocument();
    expect(screen.queryAllByText(/\u20b9/, { selector: ".mrp" }).length).toBe(0);
  });

  it("shows MRP + savings only when the backend supplies a valid MRP", () => {
    render(
      <ComparePanel
        card={card([
          offer("Flipkart", 59900, { mrp: 79900 }),
          offer("Amazon", 61999),
        ])}
        onClose={() => {}}
      />
    );
    expect(screen.getByText("\u20b979,900", { selector: ".mrp" })).toBeInTheDocument();
    expect(screen.getByText("Save \u20b920,000 (25%)")).toBeInTheDocument();
  });

  it("declines to display availability the backend never supplied", () => {
    render(
      <ComparePanel
        card={card([offer("Flipkart", 59900), offer("Amazon", 61999)])}
        onClose={() => {}}
      />
    );
    expect(screen.queryByText("In stock")).not.toBeInTheDocument();
    expect(screen.queryByText("Out of stock")).not.toBeInTheDocument();
  });

  it("surfaces availability when the backend supplies it", () => {
    render(
      <ComparePanel
        card={card([
          offer("Flipkart", 59900, { in_stock: true }),
          offer("Amazon", 61999, { availability: "Only 2 left" }),
        ])}
        onClose={() => {}}
      />
    );
    expect(screen.getByText("In stock")).toBeInTheDocument();
    expect(screen.getByText("Only 2 left")).toBeInTheDocument();
  });

  it("shows an honest 'No image' fallback when no image is supplied", () => {
    render(
      <ComparePanel
        card={card([offer("Flipkart", 59900), offer("Amazon", 61999)])}
        onClose={() => {}}
      />
    );
    expect(screen.getAllByText("No image").length).toBeGreaterThanOrEqual(2);
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("renders offer images when supplied and falls back to the card image", () => {
    render(
      <ComparePanel
        card={card([
          offer("Flipkart", 59900, { image: "https://img.example/fk.jpg" }),
          offer("Amazon", 61999),
        ])}
        onClose={() => {}}
      />
    );
    const imgs = document.querySelectorAll("img.compare-thumb");
    expect(imgs.length).toBe(2);
    expect(imgs[0]).toHaveAttribute("src", "https://img.example/fk.jpg");
    // Amazon has no own image -> it falls back to the group-level card image.
    expect(imgs[1]).toHaveAttribute("src", "https://img.example/fk.jpg");
    expect(screen.queryByText("No image")).not.toBeInTheDocument();
  });

  it("keeps View Deal links safe and pointing at the real product URL", () => {
    render(
      <ComparePanel
        card={card([
          offer("Flipkart", 59900),
          offer("Amazon", 61999, { url: "https://www.amazon.in/dp/B0XYZ" }),
        ])}
        onClose={() => {}}
      />
    );
    const links = screen.getAllByRole("link", { name: /View deal on/ });
    expect(links.length).toBe(2);
    for (const link of links) {
      expect(link).toHaveAttribute("target", "_blank");
      expect(link).toHaveAttribute("rel", "noopener noreferrer");
    }
    expect(links[0]).toHaveAttribute("href", "https://example.com/flipkart/59900");
    expect(links[1]).toHaveAttribute("href", "https://www.amazon.in/dp/B0XYZ");
  });

  it("shows marketplace filters only for marketplaces that actually have offers", () => {
    const { rerender } = render(
      <ComparePanel
        card={card([offer("Flipkart", 59900), offer("Amazon", 61999)])}
        onClose={() => {}}
      />
    );
    const group = screen.getByRole("group", { name: "Filter offers by marketplace" });
    expect(within(group).getByRole("button", { name: "All Stores" })).toBeInTheDocument();
    expect(within(group).getByRole("button", { name: "Flipkart" })).toBeInTheDocument();
    expect(within(group).getByRole("button", { name: "Amazon" })).toBeInTheDocument();
    expect(within(group).queryByRole("button", { name: "Myntra" })).not.toBeInTheDocument();

    // A single-marketplace group gets no marketplace filter at all.
    rerender(
      <ComparePanel card={card([offer("Flipkart", 59900)])} onClose={() => {}} />
    );
    expect(screen.queryByRole("group", { name: "Filter offers by marketplace" })).not.toBeInTheDocument();
  });

  it("filters offers by marketplace inside the panel", () => {
    const { container } = render(
      <ComparePanel
        card={card([offer("Flipkart", 59900), offer("Amazon", 61999)])}
        onClose={() => {}}
      />
    );
    expect(rowPlatforms(container).length).toBe(2);

    fireEvent.click(screen.getByRole("button", { name: "Amazon" }));
    expect(rowPlatforms(container)).toEqual(["Amazon"]);

    fireEvent.click(screen.getByRole("button", { name: "All Stores" }));
    expect(rowPlatforms(container)).toEqual(["Flipkart", "Amazon"]);
  });

  it("sorts offers by price inside the panel with deterministic ties", async () => {
    const user = (await import("@testing-library/user-event")).default;
    const { container } = render(
      <ComparePanel
        card={card([offer("Myntra", 950), offer("Flipkart", 899), offer("Amazon", 1200)])}
        onClose={() => {}}
      />
    );

    // Default: best price first (ascending).
    expect(rowPrices(container)).toEqual(["\u20b9899", "\u20b9950", "\u20b91,200"]);

    await user.selectOptions(screen.getByLabelText("Sort offers"), "price-desc");
    expect(rowPrices(container)).toEqual(["\u20b91,200", "\u20b9950", "\u20b9899"]);

    await user.selectOptions(screen.getByLabelText("Sort offers"), "price-asc");
    expect(rowPrices(container)).toEqual(["\u20b9899", "\u20b9950", "\u20b91,200"]);
  });

  it("closes on Escape and focuses the close button first", () => {
    const onClose = vi.fn();
    render(<ComparePanel card={card([offer("Flipkart", 59900), offer("Amazon", 61999)])} onClose={onClose} />);

    expect(screen.getByRole("button", { name: "Close comparison" })).toHaveFocus();

    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});