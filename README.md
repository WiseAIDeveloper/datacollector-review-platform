# Datacollector Review Platform

Open http://10.1.1.49:8769 on the internal network. No login is required.

Open http://10.1.1.49:8769/coverage.html for the identity coverage dashboard. It compares each identity with `internal_colour_print_enhancement_2.csv`, shows missing, over-count and complete matrix groups, and supports batch review decisions using the same browser storage and exports as the main page.

Filter by identity, folder, lighting, SDK and device. Select two captures to compare images and metadata. Use Keep, Remove, Correct metadata or Undecided, add notes, then export JSON or CSV for review. Decisions are saved in browser storage and do not modify the dataset. Export before switching browsers or clearing browser storage.

Dataset access is read-only. Refresh captures reads current CSVs.

Manage from this directory:

    docker compose up -d --build
    docker compose logs --tail 50
    docker compose down

## Ingestion logs

Open `/ingestion.html` from the sidebar. A server worker scans every five seconds,
independently of browser visits. Each unique batch/UUID/filename is logged once
when its annotation CSV row and nonempty original image are present. Initial
captures are labelled Existing; later detections are Ingested. Detection time
is not the original upload time. Metadata is a snapshot at detection. This page
monitors ingestion; it does not upload files or change annotations.

History persists in the `ingestion_state` Docker volume at `/state/ingestion.sqlite`.
Deleted captures stay in history. Removing and restoring the same capture key
does not create another event. Do not remove this volume if history is needed.
The API `/api/ingestion?limit=100&before=123` provides newest-first pagination.
Missing images and CSV read errors are retried on the next scan.

Run scanner tests: `python3 -m unittest discover -s . -p test_ingestion.py -v`
(from this directory). Browser checks: `python3 test_ingestion_browser.py`.

The dashboard now supports PIN-protected execution of marked Remove decisions.
Marking alone only saves a browser decision. Execution deletes matching CSV rows
and image files after confirmation; JSON collection metadata remains.

## Source location

App source lives in `/home/jingjie/services/datacollector-review-platform`. The dataset remains at
`/mnt5/auto-ekyc/idrecapture`. Runtime logs and the protected deletion PIN remain
in `/mnt5/auto-ekyc/idrecapture/capture_viewer` and are referenced by absolute
paths in `compose.yaml`. The existing `capture_viewer_ingestion_state` Docker
volume holds ingestion history.

The source was relocated without restarting or redeploying the running container.
Run future Compose commands from this directory when deployment is requested.

Compose keeps the existing project name `capture_viewer` so future deployments
reuse the current container and ingestion volume after the source folder rename.
