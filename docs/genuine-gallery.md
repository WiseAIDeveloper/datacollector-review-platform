# Numbered genuine image gallery

This optional mode shows the same numbered genuine reference images for every
batch. Use the dashboard-style buttons to choose a batch, then one phone + lighting combination configured in that
batch's matrix. A card turns green as soon as at least one collected capture in
that batch and combination has the same number in its `subject` field. The card
also shows the matching sample count. The page refreshes every five seconds while
visible. Search narrows the cards by number; the slider shows 2, 4, or 8 images
per row. Portrait frames display each full reference photo, and clicking a photo
opens a larger view with zoom and pan. On narrow screens, wider settings scroll
sideways. Card links open the
existing Capture review, Coverage, and Quality review pages for that number and
batch; Capture review also uses the selected phone and lighting filters. The
existing pages and APIs remain available.

## Reference manifest

Set `GENUINE_REFERENCE_CSV` to a private CSV with `assigned_number` and
`absolute_ori_path` columns. Numbers must be unique positive integers; paths
must be absolute and point to readable JPEG, PNG, or WebP originals. The gallery
uses only these two columns. Keep this CSV and its source images outside Git.
Do not reorder or renumber the manifest after collection begins: collectors enter
the assigned number and the matching relies on that exact value.

For the 50-image sample, the private, Git-ignored numbered copy in `artifacts/`
uses source row order as numbers 1–50. It is a local test manifest, not a tracked
fixture or a production migration. The source CSV and images were not modified.

## Run

For a local source run, set `GENUINE_REFERENCE_CSV` in the service environment
alongside the usual dataset and state settings. Without it, normal mode behaves
as before and the gallery API returns 404.

For Docker, add `compose.genuine.yaml` to the existing folder-project Compose
command. Place the manifest at `${GENUINE_REFERENCES_DIR}/manifest.csv` and set
`GENUINE_IMAGE_ROOT` to a single absolute directory containing all reference
images. The container mounts that directory at the same absolute path because
the CSV contains absolute paths. Keep the existing service on its configured port;
use an isolated preview when testing a branch.

```sh
docker compose --env-file .env.projects \
  -f compose.projects.yaml -f compose.genuine.yaml up -d --build --wait
```

The `subject` field in the collected capture CSV must contain the assigned number
as entered by the collector. If the collector writes that number elsewhere, map it
to `subject` before relying on the status cards. No genuine source path or session
ID is sent in the gallery summary API; image bytes are served only for configured
numbers. Restrict access to this service and its reference images before using
genuine production data.
