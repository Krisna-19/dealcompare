/* Cosmetic store identity for offer rows in both the product cards and the
   comparison panel.  Purely presentational — platform names always come from
   the API; an unknown/new marketplace degrades to a neutral tone, never hidden. */

export const STORE_META = {
  Flipkart: { initials: "FL", color: "#1f6feb", text: "#FFFFFF" },
  Amazon: { initials: "AZ", color: "#ff9900", text: "#0b0b0b" },
  Myntra: { initials: "MY", color: "#ff3f6c", text: "#FFFFFF" },
  Ajio: { initials: "AJ", color: "#111827", text: "#FFFFFF" },
  Croma: { initials: "CR", color: "#1d4ed8", text: "#FFFFFF" },
  "Tata CLiQ": { initials: "TC", color: "#0f766e", text: "#FFFFFF" },
  Meesho: { initials: "MS", color: "#c2410c", text: "#FFFFFF" },
};

export function storeMeta(platform) {
  const known = STORE_META[platform];
  if (known) return known;
  const initials = (platform || "ST").slice(0, 2).toUpperCase();
  return { initials, color: "#4b5563", text: "#FFFFFF" };
}