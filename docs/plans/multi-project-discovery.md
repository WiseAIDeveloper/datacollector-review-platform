# Project discovery proposal

Status: draft for discussion. Saved on 2026-09-15.

This document records the user's prompts and the proposed approach before implementation.
The project root, standard filenames, and CSV requirements below are proposed conventions.

## User prompts

### Supporting multiple workflows

> do you have any idea of how this can be more fuild? supporting multiple data collection workflows, for different directory, all at once?

### Project folders and two required CSVs

> or perhaps we can keep a folder in the mnt5 (our dataset location) and add this path inside , then each subfolder will be the datacollection project, inside will have 2 required csvs? then we select the "project" what do you think？

### Save the proposal first

> temporary create a branch and throw my prompt and this md in first

## Proposed approach

Yes—that’s a good fit: **one parent directory, one subfolder per project, and a project selector in the app.**

### Proposed layout

```text
/mnt5/datacollection-projects/
├── id-recapture/
│   ├── matrix.csv
│   ├── batches.csv
│   └── data/
│       └── batch-a/
│           ├── index_annotation_.csv
│           ├── index_annotation_mykadfront.csv
│           └── mykadfront/
└── passport-collection/
    ├── matrix.csv
    ├── batches.csv
    └── data/
        └── ...
```

For the **two required project-level CSVs**, I’m assuming you mean:

- **`matrix.csv`** — expected collection coverage and counts.
- **`batches.csv`** — batch definitions and collection settings.

The capture annotation CSVs remain inside each data batch.

### How it would work

1. Configure the parent directory once.
2. The app discovers its immediate subfolders as projects.
3. Validate each project’s required files and columns. Show incomplete projects with a clear explanation.
4. Select a project to view its captures, coverage, reviews, and logs.
5. Keep ingestion running for all valid projects, regardless of which is selected.

Each project gets separate history and review drafts. Every read or write carries the project ID, so identical capture IDs in different projects stay separate.

Mounting the parent directory into Docker makes its project folders accessible to the app. [Docker documentation](https://docs.docker.com/engine/storage/bind-mounts/)

**Adding a project would then mean creating its folder and supplying the required files—no code change.** The CSVs would need a shared, documented column format. This would also let us remove project-specific filenames and test-plan values from the code.
