/* Create projects with a validated pair of CSVs and open scoped dashboards. */
const list = document.getElementById("project-list");
const listStatus = document.getElementById("list-status");
const createStatus = document.getElementById("create-status");

async function loadProjects() {
  /* Render project names as text and offer a stable URL for each selection. */
  try {
    const response = await fetch("/api/projects");
    if (!response.ok) throw new Error(await response.text());
    const projects = await response.json();
    list.replaceChildren();
    listStatus.textContent = projects.length
      ? `${projects.length} projects available`
      : "No projects yet. Upload two CSVs to get started.";
    for (const project of projects) {
      const card = document.createElement("article");
      const title = document.createElement("h3");
      title.textContent = project.name;
      const plan = document.createElement("p");
      plan.textContent = project.matrix_name;
      const open = document.createElement("a");
      open.href = "/coverage.html?project=" + encodeURIComponent(project.id);
      open.textContent = "Open project";
      if (new URLSearchParams(location.search).get("project") === project.id)
        open.textContent = "Open selected project";
      card.append(title, plan, open);
      list.append(card);
    }
  } catch (error) {
    listStatus.textContent = "Could not load projects: " + error.message;
  }
}

async function readCSV(id) {
  /* Decode uploaded CSV bytes strictly so invalid encodings cannot be silently saved. */
  const file = document.getElementById(id).files[0];
  if (!file || file.size > 400000 || !file.size)
    throw new Error("Select two nonempty CSV files, up to 400 KB each.");
  return new TextDecoder("utf-8", { fatal: true }).decode(
    await file.arrayBuffer(),
  );
}

document
  .getElementById("project-form")
  .addEventListener("submit", async (event) => {
    /* Submit both files as one authenticated operation and retain inputs on failure. */
    event.preventDefault();
    const button = document.getElementById("create");
    button.disabled = true;
    createStatus.textContent = "Validating and creating project…";
    try {
      const [matrixCSV, batchesCSV] = await Promise.all([
        readCSV("matrix"),
        readCSV("batches"),
      ]);
      const response = await fetch("/api/projects", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Delete-Token": document.getElementById("pin").value,
        },
        body: JSON.stringify({
          name: document.getElementById("name").value,
          matrix_csv: matrixCSV,
          batches_csv: batchesCSV,
        }),
      });
      if (!response.ok) throw new Error(await response.text());
      const project = await response.json();
      document.getElementById("project-form").reset();
      createStatus.replaceChildren(
        document.createTextNode("Project created. "),
      );
      const open = document.createElement("a");
      open.href = "/coverage.html?project=" + encodeURIComponent(project.id);
      open.textContent = "Open " + project.name;
      createStatus.append(open);
      await loadProjects();
    } catch (error) {
      createStatus.textContent = "Could not create project: " + error.message;
    } finally {
      button.disabled = false;
    }
  });
loadProjects();
