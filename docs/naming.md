# Standard names

One JSON file defines, for every project, which column each value is read from
and which values are accepted. Set `NAMING_FILE` to its path to enable it;
without it, the platform keeps its previous behavior and reports no naming
issues.

The file lives at
`/mnt5/auto-ekyc/datacollection_review/idrecapture/naming/naming.json`.
`compose.projects.yaml` mounts that folder (`NAMING_PATH`) read-only at `/naming`
and sets `NAMING_FILE=/naming/naming.json`. Mount the folder, not the file:
editors that save by replacing the file would otherwise leave the container on
the old version.

```json
{
  "lighting": {
    "description": "Lighting chosen in the collector",
    "column": "lighting",
    "accepted": ["office_white", "office_yellow", "office_dark", "random_bg"]
  },
  "identity": {
    "description": "Person holding the card",
    "column": "subject",
    "accepted": ["ang-kuan-liang", "heng-zen-kit"]
  },
  "device": {
    "description": "Phone used for the capture",
    "app": { "column": "capture_device", "fallback": "input_sensor.model" },
    "web": { "column": "capture_device" },
    "accepted": {
      "galaxy_z_fold_5": {
        "capture_device": ["samsung-galaxy-z-fold-5"],
        "input_sensor.model": ["SM-F946U1"]
      },
      "iphone_13": { "capture_device": ["iphone-13"] }
    }
  },
  "replay_device": {
    "description": "Screen the card image is replayed on",
    "column": "replay_device",
    "accepted": {
      "galaxy_z_fold_5": ["samsung-galaxy-z-fold-5"],
      "iphone_13": ["iphone-13"]
    }
  }
}
```

## Blocks

`lighting`, `identity`, and `device` are all required; `replay_device` is
optional. `description` is optional free text.

| Key        | Meaning                                                                                 |
| ---------- | --------------------------------------------------------------------------------------- |
| `column`   | The one column the value is read from.                                                  |
| `fallback` | Optional column read only when `column` is empty.                                       |
| `accepted` | Lighting and identity: the exact accepted values. Device: standard names and spellings. |

`replay_device` has a `column` (no `fallback`) and no SDK blocks. `device` has an `app` and a `web` block, each with its own `column` and optional
`fallback`. The SDK itself is still detected from `input_sensor`.

A column is an index CSV column name, `input_sensor.model` (the model the App
SDK auto-detects; `Unknown` counts as empty), or `annotation.<key>` (a key in the
capture's collection annotation JSON).

## Accepted values

- **Lighting** must exactly equal an accepted value. Lighting is never
  translated.
- **Identity** must exactly equal an accepted value. An empty list disables the
  identity check; a missing identity is still flagged.
- **Device**: each key of `device.accepted` is a standard name, which always
  matches itself. Under it, each column name lists other spellings found in
  _that column_. A value read from `capture_device` is looked up only under
  `capture_device`, and a detected model only under `input_sensor.model`. Only
  columns that `device.app` or `device.web` read may be listed. A spelling may
  appear once per column and may not itself be a standard name.
- **Replay device**: each key of `replay_device.accepted` is a standard name,
  and its list holds other spellings of it (usually the same ones as its
  `capture_device` spellings). An empty value is not an issue, because genuine
  captures have no replay device; any other unlisted value is flagged. Without
  the block, replay devices are not checked.

Values are compared exactly after trimming spaces.

## Behavior

- Captures are standardized when read. Collector files are never rewritten by
  this check; the capture's raw values stay in its metadata.
- Missing or unaccepted values are highlighted with the reason, including the
  column they were read from. Fix the capture with the edit form, or add the
  value to the file.
- The edit form edits the `lighting`, `subject`, and `capture_device` columns,
  and only accepts listed lighting, identities, and standard device names.
- The file is re-read when it changes; no restart is needed. A file that is
  invalid at startup stops the service. An invalid edit while running keeps the
  last valid version and shows the error on the ingestion page.
- `python scripts/audit_project_devices.py ... --naming <file>` lists every
  unaccepted value with its capture count.

## Converting existing data

`scripts/normalize_names.py` rewrites old lighting values (given as
`--lighting old=new`) and every listed device spelling to standard names in
the capture index CSVs, collection annotation JSON, and project plan CSVs. It
is a dry run unless `--apply` is given with a new `--backup` directory, which
receives a copy of every file before it is replaced. Only the mapped cells
change; other rows keep their bytes and JSON keeps its formatting. Test and
webcam folders are skipped. Collector files are owned by root, so run it in a
container:

```sh
docker run --rm -v "$PWD":/src:ro -v /mnt5/auto-ekyc/idrecapture:/data \
  -v /mnt5/auto-ekyc/datacollection_review/idrecapture/projects:/projects \
  -v /mnt5/auto-ekyc/datacollection_review/idrecapture/naming:/naming:ro \
  -v /mnt5/auto-ekyc/datacollection_review/backups:/backups \
  python:3.10.10-slim python /src/scripts/normalize_names.py \
  --dataset /data --projects-root /projects --naming /naming/naming.json \
  --lighting dark=office_dark --lighting white=office_white ... \
  --apply --backup /backups/normalize-YYYYMMDD
```

Change the collector's option values first so no new captures arrive with old
names.
