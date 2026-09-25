/* Carry explicit project selection through API requests and workspace navigation. */
(() => {
  const project = new URLSearchParams(location.search).get("project");
  const originalFetch = window.fetch.bind(window);
  const modePromise = originalFetch("/api/project-mode").then(
    async (response) => {
      /* Read the write policy before allowing a review action to proceed. */
      if (!response.ok) throw new Error("Could not load review settings");
      return response.json();
    },
  );
  // The navigation listener also reports mode-fetch failures without unhandled rejections.
  modePromise.catch(() => {});
  window.reviewWriteToken = async (message) => {
    /* Skip credential prompts only when the server explicitly disables them. */
    try {
      const mode = await modePromise;
      return mode.write_pin_required === false ? "" : prompt(message) || null;
    } catch (_) {
      alert("Could not load review settings. Refresh and try again.");
      return null;
    }
  };
  if (project) {
    window.fetch = (input, options) => {
      /* Add project context only to same-origin API calls from these pages. */
      const url = new URL(
        input instanceof Request ? input.url : input,
        location.href,
      );
      if (
        url.origin === location.origin &&
        url.pathname.startsWith("/api/") &&
        url.pathname !== "/api/projects"
      ) {
        url.searchParams.set("project", project);
        return originalFetch(
          input instanceof Request ? new Request(url, input) : url,
          options,
        );
      }
      return originalFetch(input, options);
    };
  }
  document.addEventListener("DOMContentLoaded", async () => {
    /* Display selection and preserve it when moving between review pages. */
    const phone = matchMedia("(max-width: 760px)");
    const filters = document.querySelectorAll(".header-filters");
    const sizeFilters = () => {
      /* Default to collapsed phone filters while keeping every action visible. */
      for (const filter of filters) filter.open = !phone.matches;
    };
    sizeFilters();
    phone.addEventListener("change", sizeFilters);
    const nav = document.querySelector(".app-sidebar");
    if (!nav) return;
    const link = document.createElement("a");
    link.href = "/projects.html";
    link.textContent = "Projects";
    nav.append(link);
    if (location.pathname === "/projects.html")
      link.setAttribute("aria-current", "page");
    let folderMode = false;
    try {
      const mode = await modePromise;
      folderMode = mode.folders;
      if (
        mode.genuine_gallery &&
        !nav.querySelector('a[href="/genuine.html"]')
      ) {
        const gallery = document.createElement("a");
        gallery.href = "/genuine.html";
        gallery.textContent = "Dashboard";
        nav.insertBefore(
          gallery,
          nav.querySelector('a[href="/coverage.html"]'),
        );
      }
      if (mode.genuine_gallery) {
        const coverage = nav.querySelector('a[href="/coverage.html"]');
        if (coverage) coverage.textContent = "Coverage detail";
      }
      const pin = document.getElementById("pin");
      if (pin && mode.write_pin_required === false) {
        pin.required = false;
        pin.disabled = true;
        pin.hidden = true;
        document.querySelector('label[for="pin"]').hidden = true;
      }
    } catch (_) {
      // Existing pages can still navigate while the service recovers.
    }
    if (!project) return;
    for (const anchor of nav.querySelectorAll("a")) {
      if (anchor.getAttribute("href") === "/ingestion.html" && !folderMode) {
        anchor.textContent = "Ingestion logs (all)";
        continue;
      }
      const url = new URL(anchor.href);
      url.searchParams.set("project", project);
      anchor.href = url;
    }
    const label = document.createElement("div");
    label.className = "project-context";
    label.setAttribute("role", "region");
    label.setAttribute("aria-label", "Current project");
    const identity = document.createElement("span");
    const name = document.createElement("strong");
    name.className = "current-project-name";
    name.textContent = project;
    identity.append("Project: ", name);
    const switchProject = document.createElement("a");
    switchProject.href =
      "/projects.html?project=" + encodeURIComponent(project);
    switchProject.textContent = "Switch project";
    label.append(identity, switchProject);
    const titlebar = document.querySelector(".header-titlebar");
    if (titlebar)
      titlebar.insertBefore(label, titlebar.querySelector(".header-actions"));
    else document.querySelector("header")?.prepend(label);
    try {
      const response = await fetch("/api/project");
      if (!response.ok) throw new Error(await response.text());
      const selected = await response.json();
      name.textContent = selected.name;
      name.title = selected.name;
      document.title = selected.name + " · " + document.title;
    } catch (error) {
      identity.textContent =
        "Project unavailable. Select a project to continue.";
      label.classList.add("project-unavailable");
    }
  });
})();
