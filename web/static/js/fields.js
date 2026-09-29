/* Capture fields from the naming file, shared by every review page.

   Pages never name a field themselves: they ask this module which fields exist,
   which one is the identity, which ones the matrix plans, and what their
   choices are. */
window.captureFields = (() => {
  let loading = null;
  /* Read nonempty choices from a semicolon-separated batch setting. */
  const split = (text) =>
    (text || "")
      .split(";")
      .map((v) => v.trim())
      .filter(Boolean);
  /* Describe the loaded fields and the helpers built on them. */
  const model = (all) => {
    const byKey = new Map(all.map((f) => [f.key, f]));
    return {
      all,
      identity: all.find((f) => f.role === "identity"),
      device: all.find((f) => f.role === "device"),
      /* Fields with standard values: shown as columns and filters. */
      checked: all.filter((f) => f.accepted !== null),
      /* Fields an edit may change, keyed by the index column they write. */
      editable: all.filter((f) => f.column),
      field: (key) => byKey.get(key),
      /* Fields other than identity that the matrix plans, in naming-file order. */
      planned: (matrix) =>
        all.filter(
          (f) => f.role !== "identity" && matrix.some((row) => f.key in row),
        ),
    };
  };
  return {
    /* Load the fields once per page. */
    load() {
      loading ??= fetch("/api/fields").then(async (response) => {
        if (!response.ok) throw new Error(await response.text());
        return model(await response.json());
      });
      return loading;
    },
    split,
    /* A capture's standard value for one field. */
    value: (record, key) => record?.fields?.[key] ?? "",
    /* Allowed corrections: the batch's expected_<field> list, else the naming file.

       Identity falls back to identities already annotated in the test plan, and a
       blank device means the App SDK's detected model is used. */
    choices(field, batch, rows, testPlan) {
      const listed = split(batch?.["expected_" + field.key]);
      if (field.role === "identity")
        return listed.length
          ? listed
          : [
              ...new Set(
                rows
                  .filter((r) => r.metadata.test_plan_name === testPlan)
                  .map((r) => r.identity)
                  .filter(Boolean),
              ),
            ].sort();
      const values = listed.length ? listed : field.accepted;
      if (!values) return null;
      return field.role === "device" || !field.required
        ? ["", ...values]
        : values;
    },
    /* Label for a blank choice. */
    blank: (field) =>
      field.role === "device" ? "App SDK — use input sensor" : "(missing)",
  };
})();
