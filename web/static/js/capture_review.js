let capture = null,
  editing = false,
  opening = 0;
const editable = [
  "subject",
  "lighting",
  "capture_device",
  "input_sensor",
  "user",
];
const labels = {
  subject: "Identity",
  lighting: "Lighting",
  capture_device: "Web capture device (blank for App SDK)",
  input_sensor: "Input sensor / App device metadata",
  user: "User",
};
/* Enable review actions only when a capture is ready and no edit is running. */
function controls(disabled) {
  $("save-metadata").disabled = disabled;
  $("remove-capture").disabled = disabled;
  $("review-close").disabled = editing;
}
/* Load a capture and the configured metadata choices, ignoring stale responses. */
async function openCapture(key) {
  const ticket = ++opening;
  capture = null;
  $("review-title").textContent = "Loading capture…";
  $("review-error").textContent = "";
  $("review-fields").replaceChildren();
  $("all-metadata").textContent = "";
  $("review-image").removeAttribute("src");
  controls(true);
  $("review").showModal();
  try {
    const responses = await Promise.all([
      fetch("/api/capture?key=" + encodeURIComponent(key)),
      fetch("/api/batches"),
      fetch("/api/captures"),
    ]);
    if (!responses[0].ok)
      throw Error(
        responses[0].status === 404
          ? "This capture was removed. Its log entry remains as history."
          : await responses[0].text(),
      );
    if (!responses[1].ok || !responses[2].ok)
      throw Error(
        "Unable to load metadata choices. Please reopen this capture.",
      );
    const [row, batches, rows] = await Promise.all(
      responses.map(
        /* Decode the response body as JSON. */ (res) => res.json(),
      ),
    );
    if (ticket !== opening) return;
    const batch = batches.find(
      /* Locate the item matching the selected capture or batch. */ (b) =>
        b.batch_name === row.folder &&
        b.test_plan_name === row.metadata.test_plan_name,
    );
    if (!batch)
      throw Error("This batch has no matching definition in the batches CSV.");
    const split =
      /* Read nonempty choices from a semicolon-separated batch setting. */ (
        value,
      ) =>
        (value || "")
          .split(";")
          .map(
            /* Build the corresponding display or request value for each item. */ (
              v,
            ) => v.trim(),
          )
          .filter(Boolean);
    const identities = split(batch.expected_identities);
    const choices = {
      subject: identities.length
        ? identities
        : [
            ...new Set(
              rows
                .filter(
                  /* Keep items that match the current selection criteria. */ (
                    r,
                  ) =>
                    r.metadata.test_plan_name === row.metadata.test_plan_name,
                )
                .map(
                  /* Build the corresponding display or request value for each item. */ (
                    r,
                  ) => r.metadata.subject,
                )
                .filter(Boolean),
            ),
          ].sort(),
      lighting: split(batch.expected_lighting),
      capture_device: ["", ...split(batch.expected_web_devices)],
    };
    $("review-title").textContent = row.folder + " / " + row.metadata.filename;
    $("review-image").src = "/api/image?key=" + encodeURIComponent(row.key);
    $("all-metadata").textContent = JSON.stringify(row.metadata, null, 2);
    for (const k of editable) {
      const label = document.createElement("label");
      label.textContent = labels[k];
      const input = document.createElement(
        choices[k] ? "select" : k === "input_sensor" ? "textarea" : "input",
      );
      input.id = "edit-" + k;
      const current = row.metadata[k] || "";
      if (choices[k]) {
        if (!choices[k].includes(current)) {
          const option = document.createElement("option");
          option.value = current;
          option.textContent =
            (current || "(missing)") +
            " — current value outside configured choices";
          input.append(option);
        }
        for (const value of [...new Set(choices[k])]) {
          const option = document.createElement("option");
          option.value = value;
          option.textContent =
            value ||
            (k === "capture_device"
              ? "App SDK — use input sensor"
              : "(missing)");
          input.append(option);
        }
      }
      input.value = current;
      label.append(input);
      $("review-fields").append(label);
    }
    const hint = document.createElement("p");
    hint.textContent =
      "Lighting and Web devices: batch CSV. Identities: " +
      (identities.length
        ? "batch CSV."
        : "annotated identities in this test plan.");
    $("review-fields").append(hint);
    capture = row;
    controls(false);
  } catch (e) {
    if (ticket === opening) $("review-error").textContent = e.message;
  }
}
/* Confirm and submit a metadata edit or deletion, then refresh the visible capture. */
async function executeEdit(remove) {
  if (!capture || editing) return;
  const row = capture;
  const changes = Object.fromEntries(
    editable
      .filter(
        /* Keep items that match the current selection criteria. */ (k) =>
          $("edit-" + k).value !== (row.metadata[k] || ""),
      )
      .map(
        /* Build the corresponding display or request value for each item. */ (
          k,
        ) => [k, $("edit-" + k).value],
      ),
  );
  if (!remove && !Object.keys(changes).length) {
    $("review-error").textContent = "No metadata changes.";
    return;
  }
  const question = remove
    ? "Delete " +
      row.metadata.filename +
      " from both CSV indexes and delete its images? JSON metadata and ingestion history remain."
    : "Save these metadata changes in both CSV indexes?\n" +
      Object.entries(changes)
        .map(
          /* Build the corresponding display or request value for each item. */ ([
            k,
            v,
          ]) => k + ": " + v,
        )
        .join("\n");
  if (!confirm(question)) return;
  const pin = window.reviewWriteToken
    ? await window.reviewWriteToken("Enter your PIN:")
    : prompt("Enter your PIN:") || null;
  if (pin === null) return;
  editing = true;
  controls(true);
  $("review-error").textContent = "";
  try {
    const payload = remove
      ? {
          confirm_count: 1,
          remove: [
            {
              key: row.key,
              folder: row.folder,
              uuid: row.metadata.uuid,
              filename: row.metadata.filename,
            },
          ],
        }
      : {
          folder: row.folder,
          uuid: row.metadata.uuid,
          filename: row.metadata.filename,
          changes,
          expected: row.metadata,
        };
    const res = await fetch(
      remove ? "/api/apply-decisions" : "/api/edit-capture",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Delete-Token": pin,
        },
        body: JSON.stringify(payload),
      },
    );
    if (!res.ok) throw Error(await res.text());
    if (remove) {
      try {
        const d = JSON.parse(
          localStorage.getItem("idrecapture-review-v1") || "{}",
        );
        delete d[row.key];
        localStorage.setItem("idrecapture-review-v1", JSON.stringify(d));
      } catch {}
      capture = null;
      $("review").close();
      await refresh();
    } else {
      await refresh();
      editing = false;
      await openCapture(row.key);
    }
  } catch (e) {
    $("review-error").textContent = "Not saved: " + e.message;
  } finally {
    editing = false;
    controls(!capture);
  }
}
$("review-close").onclick =
  /* Dismiss the capture and invalidate any unfinished loading response. */ () => {
    opening++;
    $("review").close();
  };
$("review").addEventListener(
  "cancel",
  /* Handle the cancel event for this control. */ (e) => {
    if (editing) e.preventDefault();
    else opening++;
  },
);
$("save-metadata").onclick =
  /* Submit the current metadata corrections. */ () => executeEdit(false);
$("remove-capture").onclick =
  /* Submit the selected capture for confirmed deletion. */ () =>
    executeEdit(true);
