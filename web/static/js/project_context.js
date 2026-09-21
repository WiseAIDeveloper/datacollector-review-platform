/* Carry explicit project selection through API requests and workspace navigation. */
(() => {
  const project = new URLSearchParams(location.search).get("project");
  const originalFetch = window.fetch.bind(window);
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
    const nav = document.querySelector(".app-sidebar");
    if (!nav) return;
    const link = document.createElement("a");
    link.href = "/projects.html";
    link.textContent = "Projects";
    nav.append(link);
    if (location.pathname === "/projects.html")
      link.setAttribute("aria-current", "page");
    if (!project) return;
    for (const anchor of nav.querySelectorAll("a")) {
      if (anchor.getAttribute("href") === "/ingestion.html") {
        anchor.textContent = "Ingestion logs (all)";
        continue;
      }
      const url = new URL(anchor.href);
      url.searchParams.set("project", project);
      anchor.href = url;
    }
    const label = document.createElement("p");
    label.setAttribute("role", "status");
    document.querySelector("header")?.prepend(label);
    try {
      const response = await fetch("/api/project");
      if (!response.ok) throw new Error(await response.text());
      const selected = await response.json();
      label.textContent = "Project: " + selected.name;
      const files = document.querySelector(".plan-files p");
      if (files)
        files.textContent =
          "Test plan and batch definitions from project: " + selected.name;
    } catch (error) {
      label.textContent =
        "Project unavailable: " +
        error.message +
        ". Select a project from Projects.";
    }
  });
})();
