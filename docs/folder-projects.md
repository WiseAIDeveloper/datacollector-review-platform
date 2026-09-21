# Folder-based project service

`compose.projects.yaml` starts a separate `idrecapture-project-review` container,
using port 8771 by default. It does not replace `idrecapture-viewer` on 8769.
The new service disables write PINs with `WRITE_PIN_REQUIRED=false`; confirmation
prompts still apply to edits and deletions. The home page is a project chooser. It discovers immediate child directories under
`PROJECTS_ROOT` on every API request; the chooser refreshes every five seconds.
A directory needs exactly one `NAME.csv` and matching `NAME_batches.csv` pair.
Optional `project.json` contains a display name: `{"name": "My project"}`.
Malformed folders appear with an error and cannot be selected.

The first project uses this layout:

```text
/mnt5/auto-ekyc/datacollection_review/idrecapture/projects/
└── 001_MyKad_ColourPrintEnhancement2/
    ├── internal_colour_print_enhancement_2.csv
    ├── internal_colour_print_enhancement_2_batches.csv
    ├── project.json
    ├── ingestion.jsonl
    ├── actions.jsonl
    ├── .imported-history/       # Exact copies and hashes of imported history
    ├── ingestion.sqlite        # Created when selected
    └── quality_reviews.json    # Created when a quality review is saved
```

Each project has its own ingestion database, JSONL logs, and quality-review JSON.
Copied JSONL files are restored transactionally before the first scan and only
once. Invalid history stops that project's startup without overwriting its logs.
Back up the entire project directory, including SQLite, when backing up reviews.
Existing captured images and annotations remain in the shared capture dataset.
Capture edits and deletions operate on that shared dataset; project selection is
not an independent copy of the images or collection annotations.

Create a private `.env.projects` with mode 600, containing `DATASET_PATH`,
`PROJECTS_PATH`, `PROJECT_REVIEW_BIND_ADDRESS`, `PROJECT_REVIEW_PORT`, and
`PROJECT_REVIEW_GID` (the numeric group owning the
project directories, obtained with `id -g` for directories created by you). The
container joins that group to access the copied files. No write PIN is needed.
For this service,
`DATASET_PATH` points to `/mnt5/auto-ekyc/idrecapture` and `PROJECTS_PATH` points to
the `projects` directory above. Bind only to the intended host interface.

```sh
python scripts/seed_folder_project.py \
  --source /mnt5/auto-ekyc/idrecapture \
  --destination /mnt5/auto-ekyc/datacollection_review/idrecapture/projects/001_MyKad_ColourPrintEnhancement2

docker compose --env-file .env.projects -f compose.projects.yaml up -d --build --wait
```

The seed command refuses to overwrite existing projects and leaves the source
files untouched. New projects can be added by copying a CSV pair into a new folder
or through the Create project form. No restart or registration step is required.
Folders must have names using letters, digits, underscores, hyphens, or periods,
starting with a letter or digit (up to 120 characters). Uploaded projects get a
safe folder name automatically.

The original `compose.yaml` and legacy mode remain supported. Set `PROJECTS_ROOT`
only for folder discovery; omit it to retain the previous single-dataset behavior.
