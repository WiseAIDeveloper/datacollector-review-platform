/* Show numbered genuine images and update their collection status in place. */
const gallery = document.getElementById("genuine-cards");
const galleryStatus = document.getElementById("gallery-status");
const galleryError = document.getElementById("gallery-error");
const search = document.getElementById("number-search");
const project = new URLSearchParams(location.search).get("project");
const cards = new Map();
let loading = false;

function workspaceUrl(path, number) {
  /* Keep the selected project and assigned number in review navigation. */
  const url = new URL(path, location.href);
  if (project) url.searchParams.set("project", project);
  url.searchParams.set("subject", number);
  return url.pathname + url.search;
}

function createCard(number) {
  /* Build one image card without placing source paths or session IDs in the page. */
  const article = document.createElement("article");
  article.className = "genuine-card";
  article.dataset.number = number;
  const image = document.createElement("img");
  image.loading = "lazy";
  image.alt = "Genuine image number " + number;
  image.src =
    "/api/genuine-image?number=" +
    encodeURIComponent(number) +
    (project ? "&project=" + encodeURIComponent(project) : "");
  const details = document.createElement("div");
  details.className = "card-details";
  const heading = document.createElement("h2");
  heading.textContent = "Number " + number;
  const status = document.createElement("p");
  status.className = "card-status";
  const actions = document.createElement("div");
  actions.className = "card-actions";
  for (const [label, path] of [
    ["View samples", "/"],
    ["Coverage", "/coverage.html"],
    ["Quality", "/quality.html"],
  ]) {
    const link = document.createElement("a");
    link.href = workspaceUrl(path, number);
    link.textContent = label;
    actions.append(link);
  }
  details.append(heading, status);
  article.append(details, image, actions);
  article.statusElement = status;
  cards.set(number, article);
  return article;
}

function filterCards() {
  /* Narrow the gallery by assigned number without reloading images. */
  const term = search.value.trim();
  for (const [number, card] of cards)
    card.hidden = !!term && !number.includes(term);
}

async function refreshGallery() {
  /* Poll for new captures while retaining existing image elements and focus. */
  if (loading || document.hidden) return;
  loading = true;
  try {
    const response = await fetch("/api/genuine");
    if (!response.ok) throw new Error("Could not load the genuine gallery");
    const items = await response.json();
    const seen = new Set();
    let collected = 0;
    for (const item of items) {
      const number = String(item.number);
      seen.add(number);
      const card = cards.get(number) || createCard(number);
      card.classList.toggle("collected", item.count > 0);
      card.statusElement.textContent =
        item.count > 0
          ? item.count +
            " sample" +
            (item.count === 1 ? "" : "s") +
            " collected"
          : "Waiting for samples";
      if (item.count > 0) collected++;
      gallery.append(card);
    }
    for (const [number, card] of cards) {
      if (!seen.has(number)) {
        card.remove();
        cards.delete(number);
      }
    }
    filterCards();
    galleryStatus.textContent =
      collected +
      " of " +
      items.length +
      " genuine images have samples · updates every 5 seconds";
    galleryError.textContent = "";
  } catch (error) {
    galleryError.textContent = error.message;
  } finally {
    loading = false;
  }
}

search.addEventListener("input", filterCards);
document.getElementById("refresh").addEventListener("click", refreshGallery);
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) refreshGallery();
});
refreshGallery();
setInterval(refreshGallery, 5000);
