# Naming file: the capture fields

One JSON file defines every capture field the platform shows, checks, plans, and
edits. Nothing else in the code names a field: pages, coverage, edits, audits,
and the ingestion log all follow this file. `NAMING_FILE` must point to it; the
service does not start without a valid file.

The file lives at
`/mnt5/auto-ekyc/datacollection_review/idrecapture/naming/naming.json`. Both
compose files mount its folder (`NAMING_PATH`) read-only at `/naming` and set
`NAMING_FILE=/naming/naming.json`. Mount the folder, not the file: editors that
save by replacing the file would otherwise leave the container on the old
version.

```json
{
  "subject": {
    "role": "identity",
    "description": "Person holding the card",
    "accepted": ["ang-kuan-liang", "heng-zen-kit"]
  },
  "capture_env_lighting": {
    "description": "Lighting chosen in the collector",
    "required": true,
    "accepted": ["office_white", "office_yellow", "office_dark"]
  },
  "capture_device": {
    "role": "device",
    "description": "Phone used for the capture",
    "app": { "column": "capture_device", "fallback": "input_sensor.model" },
    "web": { "column": "capture_device" },
    "accepted": {
      "galaxy_z_fold_5": {
        "capture_device": ["samsung-galaxy-z-fold-5"],
        "input_sensor.model": ["SM-F946U1"]
      },
      "iphone_14": { "capture_device": ["iphone-14"] }
    }
  },
  "replay_device": {
    "description": "Screen the card image is replayed on",
    "accepted": { "galaxy_z_fold_5": ["samsung-galaxy-z-fold-5"] }
  },
  "user": {},
  "input_sensor": {}
}
```

## One name everywhere

Each top-level key is a field. Its name is used, unchanged, as:

| Where                     | Name                                            |
| ------------------------- | ----------------------------------------------- |
| Capture index column      | `<field>` (unless `column` says otherwise)      |
| Collection annotation key | `<field>`                                       |
| Matrix column             | `<field>`: the matrix plans this field          |
| Batch choice list         | `expected_<field>`: semicolon-separated values  |
| Pages                     | the field name as the column, filter, and label |
| Ingestion log             | `<field>`: the value as captured                |

Key order is display order. To rename a field, rename its key here and run
[`scripts/rename_fields.py`](#renaming-a-field) so stored data follows.

## Blocks

| Key           | Meaning                                                                 |
| ------------- | ----------------------------------------------------------------------- |
| `role`        | `identity` or `device`; exactly one field has each role.                |
| `description` | Free text shown as a tooltip.                                           |
| `column`      | The column the value is read from; defaults to the field name.          |
| `fallback`    | A column read only when `column` is empty.                              |
| `required`    | `true` flags a missing value. Identity and device are always required.  |
| `accepted`    | A list of exact values, or standard names with their spellings (below). |

A column is an index CSV column, `input_sensor.model` (the model the App SDK
auto-detects; `Unknown` counts as empty), or `annotation.<key>` (a key in the
capture's collection annotation JSON). Fields read from the sensor model or an
annotation are shown and checked but cannot be edited.

- **Identity** (`role: identity`): the person filter and per-identity coverage.
  An empty `accepted` list disables the identity check.
- **Device** (`role: device`): has an `app` and a `web` block, each with its own
  `column` and optional `fallback`; the SDK itself is detected from
  `input_sensor`. Under each standard name, each column lists other spellings
  found in _that column_, so a label and a detected model never collide. A blank
  device edit means the App SDK's detected model is used.
- **Other fields** with an `accepted` list must match exactly. With an object,
  each key is a standard name and its list holds other spellings.
- **Free-text fields** have no `accepted`: they are editable and shown in
  capture metadata, never flagged except when `required` and missing.

Spellings may not be standard names or map to two names. Values are compared
exactly after trimming spaces.

## Plans follow the matrix

A matrix column named after a field makes that field part of coverage: a capture
counts toward a matrix row when its batch, SDK, and every planned field match.
Fields the matrix does not have, such as a replay device the plan does not use,
are ignored by coverage. The dashboard groups each batch by the first planned
field in naming-file order and lists the others per row. Batch
`expected_<field>` lists supply edit choices; without one, the field's accepted
values are offered.

## Behavior

- Captures are standardized when read. Collector files are never rewritten by
  this check; each capture's raw values stay in its metadata.
- Missing or unaccepted values are highlighted with the reason and the column
  they were read from. Fix the capture with the edit form, or add the value.
- Edits may change every field read from an index column, and only accept the
  field's standard names.
- The file is re-read when it changes; no restart is needed. An invalid edit
  while running keeps the last valid version and shows the error on the
  ingestion page.
- `python scripts/audit_project_devices.py ... --naming <file>` lists every
  unaccepted value with its capture count and checks each plan against it.

## Converting existing values

`scripts/normalize_names.py` rewrites listed spellings, and values mapped with
`--map field:old=new`, to standard names in the capture index CSVs, collection
annotation JSON, matrix columns, and `expected_<field>` batch lists. It is a dry
run unless `--apply` is given with a new `--backup` directory, which receives a
copy of every file before it is replaced. Only the mapped cells change; other
rows keep their bytes and JSON keeps its formatting. Test and webcam folders are
skipped. Collector files are owned by root, so run it in a container:

```sh
docker run --rm -v "$PWD":/src:ro -v /mnt5/auto-ekyc/idrecapture:/data \
  -v /mnt5/auto-ekyc/datacollection_review/idrecapture/projects:/projects \
  -v /mnt5/auto-ekyc/datacollection_review/idrecapture/naming:/naming:ro \
  -v /mnt5/auto-ekyc/datacollection_review/backups:/backups \
  python:3.10.10-slim python /src/scripts/normalize_names.py \
  --dataset /data --projects-root /projects --naming /naming/naming.json \
  --map capture_env_lighting:dark=office_dark ... \
  --apply --backup /backups/normalize-YYYYMMDD
```

Change the collector's option values first so no new captures arrive with old
names.

## Renaming a field

`scripts/rename_fields.py --rename old=new` renames a stored field everywhere:
capture index headers, annotation keys, plan CSV headers, and each project's
ingestion history and its JSONL logs. `--merge a,b=new` joins two plan list
columns into one. It has the same dry run, `--apply`, and `--backup` options.
Stop the review service first, since it writes the ingestion history, and rename
the collector's option field so new captures use the new name.
