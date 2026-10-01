#!/usr/bin/env python3
"""Build a PDF CV from data/*.yaml + a profile, via a Jinja2 LaTeX template.

Usage:
    build_cv.py --profile academic_full
    build_cv.py --profile short_bio

Adding a new publication: add one entry to data/publications.yaml.
Everything else (counts, first-author tally, ordering, section placement)
is recomputed automatically on the next build.
"""
import argparse
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).parent
DATA = ROOT / "data"
PROFILES = ROOT / "profiles"
TEMPLATE_DIR = ROOT / "template"
BUILD = ROOT / "build"

NAME_RE = re.compile(r"(Garc[ií]a[\s\-‐‑–]?Abadillo)", re.IGNORECASE)

LATEX_SPECIAL = {
    "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#",
    "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}", "\\": r"\textbackslash{}",
    "–": "--", "—": "---",  # en dash, em dash: not in the default T1 TFM font
    "×": r"\texttimes{}",  # multiplication sign: misrenders as a ligature otherwise
}
LATEX_RE = re.compile("|".join(re.escape(k) for k in LATEX_SPECIAL))

RAW_LATEX_KEY_NAMES = {"url", "icon", "github", "demo", "docs"}


def is_raw_latex_key(key):
    """Fields whose value is literal LaTeX (urls, icon macros) and must never be escaped."""
    return key is not None and (key in RAW_LATEX_KEY_NAMES or key.endswith(("_url", "_icon")))


def latex_escape(text: str) -> str:
    return LATEX_RE.sub(lambda m: LATEX_SPECIAL[m.group(0)], text)


def escape_tree(obj, key=None):
    """Recursively escape all string leaves, except values under URL_KEYS."""
    if isinstance(obj, dict):
        return {k: escape_tree(v, key=k) for k, v in obj.items()}
    if isinstance(obj, list):
        return [escape_tree(v, key=key) for v in obj]
    if isinstance(obj, str):
        if is_raw_latex_key(key):
            return obj
        return latex_escape(obj)
    return obj


def load_yaml(name):
    with open(DATA / f"{name}.yaml") as f:
        return yaml.safe_load(f)


def format_date(iso_date):
    return datetime.strptime(iso_date, "%Y-%m-%d").strftime("%b %d, %Y")  # e.g. "Jan 05, 2025" — fixed-width month/day


def bold_own_name(escaped_author_string: str) -> str:
    return NAME_RE.sub(lambda m: r"\textbf{" + m.group(0) + "}", escaped_author_string)


PUB_TEXT_FIELDS = ("authors", "title", "venue_detail")


def build_publications(profile_cfg):
    raw = load_yaml("publications")  # unescaped: filtering/sorting relies on exact control values

    cfg = profile_cfg.get("publications", {}) or {}
    statuses = set(cfg.get("statuses", ["published"]))
    first_author_only = cfg.get("first_author_only", False)
    max_n = cfg.get("max")

    raw = raw[::-1]  # entries are appended at the bottom of the file, so later entries count as newer
    filtered = [p for p in raw if p["status"] in statuses]
    if first_author_only:
        filtered = [p for p in filtered if p.get("first_author")]

    # escape only display text, after all filtering on raw control fields is done
    filtered = [
        {**p, **{f: latex_escape(p[f]) for f in PUB_TEXT_FIELDS}}
        for p in filtered
    ]
    for p in filtered:
        p["authors_fmt"] = bold_own_name(p["authors"])

    for p in filtered:
        p["year_fmt"] = "in press" if p["status"] == "accepted" else (p.get("year") or "n.d.")

    published = [p for p in filtered if p["status"] == "published"]
    if cfg.get("select_by") == "include_resume":
        # hand-picked list: accepted papers can be picked too (shown as "in press")
        published = [p for p in filtered if p["status"] in ("published", "accepted") and p.get("include_resume")]
        published.sort(key=lambda p: p["include_resume"])
    else:
        # first-author first, then newest to oldest; ties keep reversed YAML order (bottom entry first)
        published.sort(key=lambda p: (not p["first_author"], -(p.get("year") or 9999)))
        if max_n:
            published = published[:max_n]

    articles_published = [p for p in published if p["type"] == "article"]
    chapters_published = [p for p in published if p["type"] == "book_chapter"]
    under_revision = [p for p in filtered if p["status"] == "under_revision"]
    in_prep = [p for p in filtered if p["status"] == "in_prep"]
    # accepted: listed under Peer-Reviewed Papers as "in press", never counted as published
    accepted = [p for p in filtered if p["status"] == "accepted"]
    # first-author first (read from the author list if first_author is omitted); ties: bottom entry first
    accepted.sort(key=lambda p: not p.get("first_author", bool(NAME_RE.match(p["authors"]))))

    # stats computed off the FULL published set, not affected by `max`
    all_published = [p for p in raw if p["status"] == "published"]
    n_articles = sum(1 for p in all_published if p["type"] == "article")
    n_articles_first = sum(1 for p in all_published if p["type"] == "article" and p["first_author"])
    n_chapters = sum(1 for p in all_published if p["type"] == "book_chapter")

    papers_summary = (
        f"I have authored or co-authored {n_articles} peer-reviewed paper{'s' if n_articles != 1 else ''} "
        f"({n_articles_first} as first author)"
    )
    if accepted:
        papers_summary += f", with {len(accepted)} more accepted for publication"
    papers_summary += "."
    chapters_summary = (
        f"I have contributed to {n_chapters} book chapter{'s' if n_chapters != 1 else ''}."
    )

    return {
        "papers_summary": papers_summary,
        "chapters_summary": chapters_summary,
        "pubs_articles_published": articles_published,
        "pubs_book_chapters_published": chapters_published,
        "pubs_under_revision": under_revision,
        "pubs_in_prep": in_prep,
        "pubs_accepted": accepted,
        "_stats": {
            "n_articles_published": n_articles,
            "n_articles_first_author": n_articles_first,
            "n_book_chapters": n_chapters,
            "n_under_revision": len(under_revision),
            "n_in_prep": len(in_prep),
            "n_accepted": len(accepted),
        },
    }


def build_talks_stats():
    raw = load_yaml("talks")  # unescaped: counting relies on exact 'kind' values
    n_talks = len(raw)
    n_keynotes = sum(1 for t in raw if str(t.get("kind", "")).lower().startswith("keynote"))
    n_conference = n_talks - n_keynotes

    parts = [f"{n_conference} conference presentation{'s' if n_conference != 1 else ''}"]
    if n_keynotes:
        parts.append(f"{n_keynotes} keynote address{'es' if n_keynotes != 1 else ''}")
    summary = (
        f"I have delivered {n_talks} invited/conference talk{'s' if n_talks != 1 else ''} "
        f"({' and '.join(parts)})."
    )
    return {
        "talks_summary": summary,
        "n_talks": n_talks, "n_keynote_talks": n_keynotes, "n_conference_talks": n_conference,
    }


def build_posters_stats():
    raw = load_yaml("posters")
    n_posters = len(raw)
    summary = f"I have presented {n_posters} poster{'s' if n_posters != 1 else ''} at scientific conferences."
    return {"posters_summary": summary, "n_posters": n_posters}


SIMPLE_SECTION_FILES = {
    "work_experience": "work_experience",
    "education": "education",
    "honors_awards": "honors_awards",
    "travel_awards": "travel_awards",
    "talks": "talks",
    "posters": "posters",
    "teaching": "teaching",
    "computer_skills": "computer_skills",
    "professional_development": "professional_development",
    "software": "software",
    "memberships": "memberships",
    "editorial": "editorial",
}


def build_context(profile_name):
    profile_path = PROFILES / f"{profile_name}.yaml"
    if not profile_path.exists():
        sys.exit(f"Unknown profile: {profile_name} (looked for {profile_path})")
    with open(profile_path) as f:
        profile_cfg = yaml.safe_load(f)

    sections = profile_cfg["sections"]
    ctx = {"sections": sections, "build_date": datetime.now().strftime("%B %-d, %Y")}

    ctx["contact"] = escape_tree(load_yaml("contact"))  # url-keyed fields left unescaped

    if "research_interests" in sections:
        ri_cfg = profile_cfg.get("research_interests") or {}
        ri_file = "research_interests_short.txt" if ri_cfg.get("short") else "research_interests.txt"
        ctx["research_interests"] = latex_escape((DATA / ri_file).read_text().strip())
        ctx["keywords"] = escape_tree(load_yaml("keywords"))

    for section, filename in SIMPLE_SECTION_FILES.items():
        if section in sections:
            data = escape_tree(load_yaml(filename))
            max_n = (profile_cfg.get(section) or {}).get("max") if isinstance(profile_cfg.get(section), dict) else None
            if max_n:
                data = data[:max_n]
            if section == "work_experience":
                for job in data:
                    job["periods_fmt"] = " | ".join(job["periods"])
                    job["periods_compact"] = (
                        job["periods"][0].split(" -- ")[0] + " -- " + job["periods"][-1].split(" -- ")[-1]
                    )
            if section == "education":
                for ed in data:
                    ed["institution_short"] = ed["institution"].split(" -- ")[0].replace(" (UPM)", "~(UPM)")
            if section in ("talks", "posters"):
                cfg = profile_cfg.get(section) or {}
                if cfg.get("select_by") == "include_resume":
                    data = [e for e in data if e.get("include_resume")]
                    data.sort(key=lambda e: e["include_resume"])
                else:
                    data.sort(key=lambda e: e["date"], reverse=True)  # ISO dates sort chronologically
                for e in data:
                    e["date_fmt"] = format_date(e["date"])
            if section == "professional_development":
                data.sort(key=lambda e: int(re.search(r"\d{4}", e["date"]).group()), reverse=True)
            if section == "software":
                for s in data:
                    links = []
                    if s.get("github"):
                        links.append(f"\\href{{{s['github']}}}{{GitHub}}")
                    if s.get("demo"):
                        links.append(f"\\href{{{s['demo']}}}{{Demo}}")
                    if s.get("docs"):
                        links.append(f"\\href{{{s['docs']}}}{{Docs}}")
                    s["links_fmt"] = " | ".join(links)
            if section == "teaching":
                categories = {}
                for entry in data:
                    categories.setdefault(entry["role"], []).append(entry)
                ctx["teaching_categories"] = [
                    {"role": role, "entries": entries} for role, entries in categories.items()
                ]
                continue
            if section == "editorial":
                categories = {}
                for entry in data:
                    categories.setdefault(entry["kind"], []).append(entry)
                ctx["editorial_categories"] = [
                    {"kind": kind, "entries": entries} for kind, entries in categories.items()
                ]
                continue
            ctx[section] = data

    stats = {}

    if "publications" in sections:
        pub_result = build_publications(profile_cfg)
        stats.update(pub_result.pop("_stats"))
        ctx.update(pub_result)
    else:
        ctx.update({
            "pubs_articles_published": [], "pubs_book_chapters_published": [],
            "pubs_under_revision": [], "pubs_in_prep": [], "pubs_accepted": [],
            "papers_summary": "", "chapters_summary": "",
        })

    if "talks" in sections:
        talks_result = build_talks_stats()
        stats.update({k: v for k, v in talks_result.items() if k != "talks_summary"})
        ctx["talks_summary"] = talks_result["talks_summary"]

    if "posters" in sections:
        posters_result = build_posters_stats()
        stats.update({k: v for k, v in posters_result.items() if k != "posters_summary"})
        ctx["posters_summary"] = posters_result["posters_summary"]

    ctx["_stats"] = stats
    return ctx, profile_cfg


def render_tex(ctx, profile_name, template_name):
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        block_start_string=r"\BLOCK{",
        block_end_string="}",
        variable_start_string=r"\VAR{",
        variable_end_string="}",
        comment_start_string=r"\COMMENT{",
        comment_end_string="}",
        trim_blocks=True,
        lstrip_blocks=True,
        autoescape=False,
    )
    template = env.get_template(template_name)
    tex = template.render(**ctx)

    BUILD.mkdir(exist_ok=True)
    tex_path = BUILD / f"cv_{profile_name}.tex"
    tex_path.write_text(tex)
    return tex_path


def compile_pdf(tex_path):
    result = subprocess.run(
        ["tectonic", "--outdir", str(BUILD), str(tex_path)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr)
        sys.exit("tectonic compilation failed")
    print(result.stderr)


PUB_REQUIRED = ("type", "status", "first_author", "authors", "title", "venue_detail")
PUB_STATUSES = {"published", "accepted", "under_revision", "in_prep"}
PUB_TYPES = {"article", "book_chapter"}


def check_include_resume(entries, label, errors):
    picks = [e["include_resume"] for e in entries if e.get("include_resume")]
    for n in picks:
        if not isinstance(n, int) or isinstance(n, bool):
            errors.append(f"{label}: include_resume must be a number or false, got {n!r}")
    dupes = sorted({n for n in picks if picks.count(n) > 1})
    if dupes:
        errors.append(f"{label}: include_resume position(s) used more than once: {dupes}")


def validate_data():
    """Catch hand-editing mistakes before they silently end up in the PDF."""
    errors = []
    titles = {}

    pubs = load_yaml("publications") or []
    for i, p in enumerate(pubs, 1):
        where = f"publications.yaml entry #{i} ({str(p.get('title', '?'))[:50]!r})"
        required = [k for k in PUB_REQUIRED if not (k == "first_author" and p.get("status") == "accepted")]
        missing = [k for k in required if k not in p or p[k] in (None, "")]
        if missing:
            errors.append(f"{where}: missing {', '.join(missing)}")
            continue
        if p["status"] not in PUB_STATUSES:
            errors.append(f"{where}: status {p['status']!r} must be one of {sorted(PUB_STATUSES)}")
        if p["type"] not in PUB_TYPES:
            errors.append(f"{where}: type {p['type']!r} must be one of {sorted(PUB_TYPES)}")
        if p["status"] == "published" and not isinstance(p.get("year"), int):
            errors.append(f"{where}: published entries need a numeric year, got {p.get('year')!r}")
        if "first_author" not in p:
            pass  # optional for accepted papers
        elif not isinstance(p["first_author"], bool):
            errors.append(f"{where}: first_author must be true or false, got {p['first_author']!r}")
        elif p["first_author"] != bool(NAME_RE.match(p["authors"])):
            errors.append(f"{where}: first_author is {str(p['first_author']).lower()} but the author list says otherwise")
        titles.setdefault(p["title"].strip().lower(), []).append(where)
    check_include_resume([p for p in pubs if p.get("status") in ("published", "accepted")], "publications.yaml", errors)

    for places in titles.values():
        if len(places) > 1:
            errors.append("same title appears more than once (e.g. an accepted paper re-added as published): "
                          + "; ".join(places))

    for name in ("talks", "posters"):
        entries = load_yaml(name) or []
        for i, e in enumerate(entries, 1):
            try:
                datetime.strptime(str(e.get("date")), "%Y-%m-%d")
            except ValueError:
                errors.append(f"{name}.yaml entry #{i} ({str(e.get('title', '?'))[:50]!r}): date must be YYYY-MM-DD, got {e.get('date')!r}")
        check_include_resume(entries, f"{name}.yaml", errors)

    if errors:
        print("Data problems found, nothing was built:\n")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)


def build_one(profile_name):
    ctx, profile_cfg = build_context(profile_name)
    template_name = profile_cfg.get("template", "cv_template.tex.j2")
    tex_path = render_tex(ctx, profile_name, template_name)
    compile_pdf(tex_path)

    stats = ctx.get("_stats")
    if stats:
        print(f"\nStats for profile '{profile_name}':")
        for k, v in stats.items():
            print(f"  {k}: {v}")
    print(f"\nPDF: {BUILD / (tex_path.stem + '.pdf')}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--profile", nargs="+", default=["academic_full"],
        help="One or more profile names, or 'all' to build every profile in profiles/",
    )
    args = ap.parse_args()

    if args.profile == ["all"]:
        profile_names = sorted(p.stem for p in PROFILES.glob("*.yaml"))
    else:
        profile_names = args.profile

    validate_data()
    for profile_name in profile_names:
        print(f"\n=== Building '{profile_name}' ===")
        build_one(profile_name)


if __name__ == "__main__":
    main()
