# Standard names

One JSON file defines the allowed lighting names, standard device names, and
identities for every project. Set `NAMING_FILE` to its path to enable it; without
it, the platform keeps its previous behavior and reports no naming issues.

For the project service, keep the file beside the project folders, for example
`/projects/naming.json` inside the container (a file there is not a project), and
add `NAMING_FILE: /projects/naming.json` to the service environment.

```json
{
  "sources": {
    "lighting": {
      "field": "lighting",
      "description": "Lighting chosen in the collector"
    },
    "identity": {
      "field": "subject",
      "description": "Person holding the card"
    },
    "app_device": {
      "field": "capture_device",
      "fallback": "input_sensor.model",
      "description": "Phone label, else the model auto-detected by the App SDK"
    },
    "web_device": {
      "field": "capture_device",
      "description": "Phone selected in the Web collector"
    }
  },
  "lighting": ["office_white", "office_yellow", "office_dark", "random_bg"],
  "devices": {
    "galaxy_z_fold_5": { "app": ["SM-F946U1"] },
    "huawei_nova_7i": { "app": ["JNY-LX2"] },
    "iphone_13": {}
  },
  "identities": ["ang-kuan-liang", "heng-zen-kit"]
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

`sources` is required. Each of its four keys names one `field` to read, an
optional `fallback` field read only when `field` is empty, and an optional
`description`. A field is an index CSV column name, `input_sensor.model` (the
native model the App SDK reports; `Unknown` counts as missing), or
`annotation.<key>` (a key in the capture's collection annotation JSON).

| Key          | Read for                   |
| ------------ | -------------------------- |
| `lighting`   | Lighting of every capture  |
| `identity`   | Identity of every capture  |
| `app_device` | Device of App SDK captures |
| `web_device` | Device of Web SDK captures |

When both are empty, the value is highlighted as missing. The SDK itself is still detected from
`input_sensor`. The edit form edits the `lighting`, `subject`, and
`capture_device` columns.

## Behavior

- Captures are standardized when read. Collector files are never rewritten by
  this check; the capture's raw values stay in its metadata.
- Values that are missing, not listed, or not mapped are highlighted with the
  reason. Fix the capture with the edit form, or add the name to the file.
- Edits must use listed lighting, identity, and device names.
- The file is re-read when it changes; no restart is needed. A file that is
  invalid at startup stops the service. An invalid edit while running keeps the
  last valid version and shows the error on the ingestion page.
