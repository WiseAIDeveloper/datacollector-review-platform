# Standard names

One JSON file defines the allowed lighting names, standard device names, and
identities for every project. Set `NAMING_FILE` to its path to enable it; without
it, the platform keeps its previous behavior and reports no naming issues.

For the project service, keep the file beside the project folders, for example
`/projects/naming.json` inside the container (a file there is not a project), and
add `NAMING_FILE: /projects/naming.json` to the service environment.

```json
{
  "lighting": ["office_white", "office_yellow", "office_dark", "random_bg"],
  "devices": {
    "galaxy_z_fold_5": { "app": ["SM-F946U1"] },
    "huawei_nova_7i": { "app": ["JNY-LX2"] },
    "iphone_13": {}
  },
  "identities": ["ang-kuan-liang", "heng-zen-kit"],
  "sources": {
    "lighting": ["lighting"],
    "identity": ["subject"],
    "device": {
      "app": ["input_sensor.model", "capture_device"],
      "web": ["capture_device"]
    }
  }
}
```

## Rules

| Field    | Rule                                                                           |
| -------- | ------------------------------------------------------------------------------ |
| Lighting | Must exactly equal one listed name. Lighting is never translated.              |
| Device   | A standard device name matches itself. `app`/`web` lists map raw values to it. |
| Identity | Must be listed. An empty list disables the identity check.                     |

Values are compared exactly after trimming spaces. A raw device value may appear
only once per SDK and may not itself be a standard device name.

## Sources

`sources` states which capture column each field is read from, in priority order;
the first nonempty value is used. It is optional; the defaults are shown above.
A source is an index CSV column name, `input_sensor.model` (the native model the
App SDK reports; `Unknown` counts as empty), or `annotation.<key>` (a key in the
capture's collection annotation JSON).

When App captures have both a sensor model and a `capture_device` label and both
map to different standard devices, the capture is flagged with the disagreement.
The edit form still edits the `lighting`, `subject`, and `capture_device` columns.

## Behavior

- Captures are standardized when read. Collector files are never rewritten by
  this check; the capture's raw values stay in its metadata.
- Values that are missing, not listed, or not mapped are highlighted with the
  reason. Fix the capture with the edit form, or add the name to the file.
- Edits must use listed lighting, identity, and device names.
- The file is re-read when it changes; no restart is needed. A file that is
  invalid at startup stops the service. An invalid edit while running keeps the
  last valid version and shows the error on the ingestion page.
