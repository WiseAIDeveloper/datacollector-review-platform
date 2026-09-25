/* Show numbered genuine images and update their collection status in place. */
const gallery = document.getElementById("genuine-cards");
const galleryStatus = document.getElementById("gallery-status");
const galleryError = document.getElementById("gallery-error");
const search = document.getElementById("number-search");
const batchChoices = document.getElementById("batch-choices");
const combinationChoices = document.getElementById("combination-choices");
const density = document.getElementById("density");
const zoom = document.getElementById("zoom");
const project = new URLSearchParams(location.search).get("project");
const cards = new Map();
const columns = [2, 4, 8];
let matrixRows = [];
let currentRequest = null;
let batchName = "";
let combinationIndex = -1;
let availableBatches = [];

function apiUrl(path, parameters = {}) {
  /* Scope gallery requests to the project shown in this browser tab. */
  const url = new URL(path, location.href);
  if (project) url.searchParams.set("project", project);
  for (const [key, value] of Object.entries(parameters))
    url.searchParams.set(key, value);
  return url.pathname + url.search;
}

function selectedRequirement() {
  /* Return the configured combination currently selected for this batch. */
  const row = matrixRows[combinationIndex];
  return row?.folder === batchName ? row : null;
}

function workspaceUrl(path, number) {
  /* Carry the current batch, capture combination, and number into review pages. */
  const url = new URL(path, location.href);
  const requirement = selectedRequirement();
  if (project) url.searchParams.set("project", project);
  url.searchParams.set("subject", number);
  if (requirement) {
    url.searchParams.set("batch", requirement.folder);
    if (path === "/") {
      for (const field of ["lighting", "sdk", "device"])
        url.searchParams.set(field, requirement[field]);
    }
  }
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
  const imageButton = document.createElement("button");
  imageButton.type = "button";
  imageButton.className = "reference-image";
  imageButton.setAttribute(
    "aria-label",
    "Enlarge genuine image number " + number,
  );
  imageButton.append(image);
  imageButton.addEventListener("click", () => {
    /* Show the full reference image with the shared zoom and pan controls. */
    const enlarged = zoom.querySelector("img");
    enlarged.src = image.src;
    enlarged.alt = image.alt;
    zoom.showModal();
  });
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
    link.dataset.path = path;
    link.textContent = label;
    actions.append(link);
  }
  details.append(heading, status);
  article.append(details, imageButton, actions);
  article.statusElement = status;
  cards.set(number, article);
  return article;
}

function updateCardLinks(card, number) {
  /* Keep normal review links aligned with the active batch and combination. */
  for (const link of card.querySelectorAll(".card-actions a"))
    link.href = workspaceUrl(link.dataset.path, number);
}

function filterCards() {
  /* Narrow the gallery by assigned number without reloading images. */
  const term = search.value.trim();
  for (const [number, card] of cards)
    card.hidden = !!term && !number.includes(term);
}

function renderBatchChoices() {
  /* Match the normal dashboard's pressed batch buttons. */
  batchChoices.replaceChildren();
  for (const name of availableBatches) {
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.batch = name;
    button.textContent = name;
    button.setAttribute("aria-pressed", String(name === batchName));
    button.addEventListener("click", () => {
      if (name === batchName) return;
      batchName = name;
      renderBatchChoices();
      [...batchChoices.children]
        .find((choice) => choice.dataset.batch === name)
        ?.focus();
      renderCombinations();
      refreshGallery(true);
    });
    batchChoices.append(button);
  }
}

function renderCombinations(previous) {
  /* Offer the configured phone and lighting combinations as pressed buttons. */
  const indexes = matrixRows.flatMap((row, index) =>
    row.folder === batchName ? [index] : [],
  );
  combinationIndex =
    indexes.find((index) =>
      previous
        ? ["folder", "lighting", "sdk", "device"].every(
            (field) => matrixRows[index][field] === previous[field],
          )
        : false,
    ) ??
    indexes[0] ??
    -1;
  combinationChoices.replaceChildren();
  for (const index of indexes) {
    const row = matrixRows[index];
    const button = document.createElement("button");
    button.type = "button";
    button.textContent =
      row.device + " · " + row.lighting + " · " + row.sdk.toUpperCase();
    button.setAttribute("aria-pressed", String(index === combinationIndex));
    button.addEventListener("click", () => {
      combinationIndex = index;
      for (const choice of combinationChoices.children)
        choice.setAttribute("aria-pressed", String(choice === button));
      refreshGallery(true);
    });
    combinationChoices.append(button);
  }
}

async function loadOptions() {
  /* Load valid batch and phone/lighting choices from the selected project. */
  try {
    const previous = selectedRequirement();
    const [batchResponse, matrixResponse] = await Promise.all([
      fetch(apiUrl("/api/batches")),
      fetch(apiUrl("/api/matrix")),
    ]);
    if (!batchResponse.ok || !matrixResponse.ok)
      throw new Error("Could not load batch choices");
    const [definitions, requirements] = await Promise.all([
      batchResponse.json(),
      matrixResponse.json(),
    ]);
    matrixRows = requirements;
    availableBatches = [
      ...new Set(
        definitions
          .map((definition) => definition.batch_name)
          .filter((name) => matrixRows.some((row) => row.folder === name)),
      ),
    ];
    batchName = availableBatches.includes(batchName)
      ? batchName
      : availableBatches[0] || "";
    renderBatchChoices();
    renderCombinations(previous);
    if (!selectedRequirement())
      throw new Error("This project has no phone + lighting choices");
    galleryError.textContent = "";
    refreshGallery(true);
  } catch (error) {
    galleryError.textContent = error.message;
    galleryStatus.textContent = "No collection status available.";
    gallery.replaceChildren();
    cards.clear();
  }
}

function setDensity() {
  /* Keep the selected number of image columns exact, with sideways scroll if needed. */
  const count = columns[Number(density.value)] || 4;
  gallery.style.setProperty("--gallery-columns", count);
  document.getElementById("density-value").value = String(count);
  density.setAttribute("aria-valuetext", count + " images per row");
}

async function refreshGallery(force = false) {
  /* Poll only the selected combination, retaining image elements and focus. */
  if (document.hidden || (currentRequest && !force)) return;
  const requirement = selectedRequirement();
  if (!requirement) return;
  currentRequest?.abort();
  const request = new AbortController();
  currentRequest = request;
  try {
    const query = {
      batch: requirement.folder,
      lighting: requirement.lighting,
      sdk: requirement.sdk,
      device: requirement.device,
    };
    const response = await fetch(apiUrl("/api/genuine", query), {
      signal: request.signal,
    });
    if (!response.ok) throw new Error("Could not load the genuine gallery");
    const items = await response.json();
    const seen = new Set();
    let collected = 0;
    for (const item of items) {
      const number = String(item.number);
      seen.add(number);
      const card = cards.get(number) || createCard(number);
      updateCardLinks(card, number);
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
      " collected · updates every 5 seconds";
    galleryError.textContent = "";
  } catch (error) {
    if (error.name !== "AbortError") galleryError.textContent = error.message;
  } finally {
    if (currentRequest === request) currentRequest = null;
  }
}

search.addEventListener("input", filterCards);
density.addEventListener("input", setDensity);
document.getElementById("refresh").addEventListener("click", loadOptions);
document
  .getElementById("close-zoom")
  .addEventListener("click", () => zoom.close());
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) refreshGallery(true);
});
setDensity();
loadOptions();
setInterval(refreshGallery, 5000);
