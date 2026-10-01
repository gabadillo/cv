# CV builder

Turns the data files in `data/` into a PDF, using a LaTeX template.

## One-time setup

```
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
brew install tectonic
```

## Render the PDF

```
cd ~/Desktop/cv
.venv/bin/python build_cv.py --profile academic_full
```

Output: `build/cv_academic_full.pdf`

Resume (one-page, compact):

```
.venv/bin/python build_cv.py --profile resume
```

Output: `build/cv_resume.pdf`

Build both in one command:

```
.venv/bin/python build_cv.py --profile academic_full resume
```

(`--profile all` builds every profile under `profiles/`.)

`resume` is a one-page, industry-facing version (compact layout, its own template)
with a short research summary, single-line education, 2-3 line work experience blurbs,
selected publications, selected talks, software, and skills. It reads
`data/research_interests_short.txt` and each work experience entry's
`responsibilities_short` field instead of the full versions the CV uses.

Which publications/talks appear on the resume — and in what order — is controlled by
an `include_resume` field on each entry in `data/publications.yaml` / `data/talks.yaml`:
set it to a number (1, 2, 3, ...) to include that entry at that position, or to `false`
to leave it off. This is curation, not a "top N" cutoff — pick exactly which ones
represent you best.

## Adding a new publication, talk, poster, award, etc.

Open the matching file in `data/` (e.g. `data/publications.yaml`) and add one entry,
following the format of the existing entries. Add new entries at the **bottom** of the file.
Publications are shown first-author first, then newest to oldest by year; within the same year,
entries lower in the file come first. Then re-run the render command above.
Counts, first-author tally, ordering, and the footer's "Last updated" date all update
automatically — nothing else to edit by hand.

## Safety checks

Every build first checks the data and stops (building nothing) if it finds a problem, listing
each one: missing fields, a typo in `status`/`type`, a published paper without a year,
`first_author` not matching the author list, the same title twice, two entries with the same
`include_resume` number, or a talk/poster date not in `YYYY-MM-DD` form.

## Accepted (not yet published) papers

Add them to `data/publications.yaml` like any other paper, with `status: accepted`. They are
listed at the bottom of Peer-Reviewed Papers under a blue **Accepted** label, bulleted, shown as
"(in press)" (any `year` is ignored), and not counted in the published total; the summary line
adds ", with N more accepted for publication". `first_author` is optional for them. When the paper
comes out, change `status` to `published` and set its `year`.

## Adding a new profile (a trimmed version of the CV)

Copy `profiles/resume.yaml` (or `profiles/academic_full.yaml`) to a new file under
`profiles/`, adjust which sections it includes and any limits (e.g. `max` publications),
then render with `--profile <your_new_profile_name>`. A profile can also set `template:`
to point at a different `.tex.j2` file if it needs a different layout, not just a
different subset of sections.

## Files

- `data/*.yaml`, `data/*.txt` — the actual content, one file per section
- `profiles/*.yaml` — which sections (and how much of each) go into a given version of the CV,
  and which template to render them with
- `template/cv_template.tex.j2` — the full academic CV layout
- `template/resume_template.tex.j2` — the compact one-page resume layout
- `build_cv.py` — reads the data + profile, renders the LaTeX, compiles the PDF
- `build/` — generated `.tex` and `.pdf` files (not meant to be hand-edited)
