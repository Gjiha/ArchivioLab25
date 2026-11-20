#!/usr/bin/env python3
"""
enrich_materials.py — arricchisce un elenco di materiali di studio
con i metadati dell'ultima release del repository GitHub associato.

USO
    export GITHUB_TOKEN=ghp_xxx          # opzionale, ma raccomandato (rate limit)
    python enrich_materials.py in.json out.json

SICUREZZA — requisiti rispettati
- Nessun download: gli asset delle release NON vengono scaricati.
- Nessuna esecuzione: niente eval/exec/subprocess/os.system.
- L'unico host contattato è "api.github.com" (GET JSON).
- Il campo `preview` è HTML costruito in locale, con escaping anti-XSS.

COSA VIENE LETTO DAL REPO
- Owner (fallback per `author`)
- `pushed_at` (fallback per `date` se manca la release)
- Ultima release pubblicata:
    - `published_at`    → `date`
    - `author.login`    → `author` (se ancora vuoto)
    - asset `.pdf` o `.zip` (preferendo il PDF, poi il file più grande)
        → `fileUrl`, `fileType`, `fileSize`, `downloads`

Cosa NON viene ricavato: `pages` (richiederebbe di scaricare il PDF).
È lasciato a `0`. Il campo `year` viene dedotto dal `course` quando possibile.
"""

from __future__ import annotations

import html as _html
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

GITHUB_API = "https://api.github.com"
USER_AGENT = "lab25-enrich/1.0"
REQUEST_TIMEOUT = 15
REQUEST_DELAY = 0.5  # secondi tra due chiamate API

ALLOWED_EXTENSIONS = {"pdf", "zip"}


# --------------------------------------------------------------------------- #
#  Utility                                                                    #
# --------------------------------------------------------------------------- #

def parse_github_url(url: str) -> tuple[str, str] | None:
    """Estrae (owner, repo) da vari formati. Ritorna None se non è GitHub."""
    if not url:
        return None
    url = url.strip().rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]

    if "://" not in url:
        if url.count("/") == 1:  # shorthand "owner/repo"
            owner, repo = url.split("/")
            return (owner, repo) if owner and repo else None
        url = "https://" + url  # "github.com/owner/repo"

    p = urlparse(url)
    if p.netloc.lower() not in {"github.com", "www.github.com"}:
        return None
    parts = [x for x in p.path.split("/") if x]
    if len(parts) < 2:
        return None
    owner, repo = parts[0], parts[1]
    if repo.endswith(".git"):
        repo = repo[:-4]

    # Sanifica per evitare path traversal nelle chiamate API
    if not re.fullmatch(r"[A-Za-z0-9._-]+", owner):
        return None
    if not re.fullmatch(r"[A-Za-z0-9._-]+", repo):
        return None
    return owner, repo


def human_size(n: int | float | None) -> str:
    if not n:
        return ""
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}".replace(".0 ", " ")
        n /= 1024
    return f"{n:.1f} PB"


def infer_year(course: str, year_in: Any) -> str:
    """Deduce '1'/'2'/'3'/'magistrale' dal nome del corso, se non fornito."""
    if year_in not in (None, ""):
        return str(year_in).strip()
    if not course:
        return ""
    c = course.lower()
    for token, val in (
        (r"\bprimo\b|\b1\b", "1"),
        (r"\bsecondo\b|\b2\b", "2"),
        (r"\bterzo\b|\b3\b", "3"),
        (r"\bmagistrale\b", "magistrale"),
    ):
        if re.search(token, c):
            return val
    return ""


def infer_category(course: str, category_in: Any) -> str:
    if category_in:
        return str(category_in).strip()
    if not course:
        return "Generale"
    head = re.split(r"\s+[-–—]\s+|(?<=\s)(?:1|2|3)\b", course, maxsplit=1)[0]
    return head.strip() or course.strip()


def safe_url(url: str) -> str:
    """Consente solo http/https, altrimenti stringa vuota."""
    if not url:
        return ""
    url = url.strip()
    if url.startswith(("http://", "https://")):
        return _html.escape(url, quote=True)
    return ""


# --------------------------------------------------------------------------- #
#  Preview HTML                                                               #
# --------------------------------------------------------------------------- #

def build_preview_html(m: dict) -> str:
    """Costruisce una scheda HTML autonoma (nessuna risorsa esterna)."""
    esc = lambda s: _html.escape("" if s is None else str(s), quote=True)

    tags = m.get("tags") or []
    tags_html = "".join(
        f'<span style="background:#DDE5DB;color:#414941;border-radius:9999px;'
        f'padding:2px 8px;font-size:11px;font-weight:600;margin-right:4px;">{esc(t)}</span>'
        for t in tags
    )

    file_url = safe_url(m.get("fileUrl") or "")
    file_type = esc((m.get("fileType") or "file").upper())
    file_size = esc(m.get("fileSize") or "—")

    if file_url:
        cta = (
            f'<a href="{file_url}" rel="noopener noreferrer" target="_blank" '
            f'style="display:inline-block;background:#1B5E34;color:#fff;'
            f'text-decoration:none;border-radius:9999px;padding:8px 18px;'
            f'font-weight:600;font-size:13px;">Scarica {file_type}'
            f'{" (" + file_size + ")" if file_size else ""}</a>'
        )
    else:
        cta = (
            '<span style="color:#BA1A1A;font-size:12px;">'
            'Nessun asset .pdf/.zip nell\'ultima release</span>'
        )

    return f"""<!DOCTYPE html>
<html lang="it"><head><meta charset="utf-8"><title>{esc(m.get('title'))}</title></head>
<body style="margin:0;font-family:'Segoe UI',system-ui,sans-serif;background:#F7FAF6;color:#181D18;padding:24px;">
  <div style="max-width:640px;margin:0 auto;background:#EFF4EE;border:1px solid #C1C9BF;border-radius:16px;padding:24px;">
    <h1 style="font-size:22px;margin:0 0 8px;color:#3B9B48;">{esc(m.get('title'))}</h1>
    <p style="margin:0 0 14px;color:#414941;line-height:1.55;white-space:pre-wrap;">{esc(m.get('description'))}</p>
    <p style="font-size:12px;color:#414941;margin:0 0 8px;">
      <strong>Corso:</strong> {esc(m.get('course') or '—')} &nbsp;·&nbsp;
      <strong>Autore:</strong> {esc(m.get('author') or '—')} &nbsp;·&nbsp;
      <strong>Data:</strong> {esc(m.get('date') or '—')} &nbsp;·&nbsp;
      <strong>Download:</strong> {esc(m.get('downloads') or 0)}
    </p>
    <div style="margin:10px 0 18px;">{tags_html}</div>
    {cta}
  </div>
</body></html>"""


# --------------------------------------------------------------------------- #
#  GitHub client (solo GET)                                                   #
# --------------------------------------------------------------------------- #

class GitHubClient:
    def __init__(self, token: str | None = None):
        self.token = token
        self._last_call = 0.0

    def _throttle(self) -> None:
        delta = time.time() - self._last_call
        if delta < REQUEST_DELAY:
            time.sleep(REQUEST_DELAY - delta)
        self._last_call = time.time()

    def get(self, path: str) -> Any:
        """GET api.github.com{path}. Ritorna JSON parsato oppure None."""
        self._throttle()
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        req = Request(GITHUB_API + path, headers=headers, method="GET")
        try:
            with urlopen(req, timeout=REQUEST_TIMEOUT) as r:
                return json.loads(r.read().decode("utf-8"))
        except HTTPError as e:
            if e.code == 404:
                return None
            if e.code in (403, 429):
                sys.stderr.write(f"[github] rate-limit / forbidden su {path}\n")
            else:
                sys.stderr.write(f"[github] HTTP {e.code} su {path}\n")
            return None
        except (URLError, TimeoutError, json.JSONDecodeError) as e:
            sys.stderr.write(f"[github] errore su {path}: {e}\n")
            return None

    def repo_info(self, owner: str, repo: str) -> dict | None:
        return self.get(f"/repos/{owner}/{repo}")

    def latest_release(self, owner: str, repo: str) -> dict | None:
        """Ultima release pubblicata; fallback su /releases?per_page=1 se 404."""
        rel = self.get(f"/repos/{owner}/{repo}/releases/latest")
        if rel is not None:
            return rel
        lst = self.get(f"/repos/{owner}/{repo}/releases?per_page=1")
        if isinstance(lst, list) and lst:
            return lst[0]
        return None


# --------------------------------------------------------------------------- #
#  Selezione asset                                                            #
# --------------------------------------------------------------------------- #

def pick_best_asset(assets: list[dict]) -> dict | None:
    """Tra gli asset .pdf/.zip, preferisce PDF, poi il più grande."""
    cand = []
    for a in assets or []:
        name = (a.get("name") or "").lower()
        ext = name.rsplit(".", 1)[-1] if "." in name else ""
        if ext in ALLOWED_EXTENSIONS:
            cand.append(a)
    if not cand:
        return None
    cand.sort(key=lambda a: (
        0 if (a.get("name") or "").lower().endswith(".pdf") else 1,
        -(a.get("size") or 0),
        (a.get("name") or "").lower(),
    ))
    return cand[0]


# --------------------------------------------------------------------------- #
#  Enrichment                                                                 #
# --------------------------------------------------------------------------- #

def enrich_one(item: dict, client: GitHubClient, idx: int, *, include_source_zip: bool) -> dict:
    out = {
        "id": f"mat-{idx:03d}",
        "title": item.get("title", "Materiale senza titolo"),
        "description": item.get("description", ""),
        "category": infer_category(item.get("course", ""), item.get("category")),
        "course": item.get("course", ""),
        "year": infer_year(item.get("course", ""), item.get("year")),
        "author": item.get("author", ""),
        "date": item.get("date", ""),
        "type": (item.get("type") or "appunti").lower(),
        "link_repository": item["repository_link"],
        "fileUrl": "",
        "fileType": "",
        "fileSize": "",
        "pages": 0,          # sconosciuto senza scaricare il PDF
        "downloads": 0,
        "tags": list(item.get("tags") or []),
    }

    owner_repo = parse_github_url(item.get("repository_link", ""))
    if not owner_repo:
        out["preview"] = build_preview_html(out)
        return out

    owner, repo = owner_repo

    # 1) Info generali del repo
    info = client.repo_info(owner, repo)
    if info:
        if not out["author"]:
            out["author"] = (info.get("owner") or {}).get("login") or owner
        if not out["date"]:
            pushed = info.get("pushed_at") or info.get("updated_at")
            if pushed:
                out["date"] = pushed[:10]

    # 2) Ultima release
    release = client.latest_release(owner, repo)
    if not release:
        out["preview"] = build_preview_html(out)
        return out

    if release.get("published_at"):
        out["date"] = release["published_at"][:10]
    rel_author = (release.get("author") or {}).get("login")
    if rel_author and not out["author"]:
        out["author"] = rel_author

    # 3) Asset .pdf / .zip nell'ultima release
    assets = release.get("assets") or []
    best = pick_best_asset(assets)
    if best:
        out["fileUrl"] = best.get("browser_download_url") or ""
        name = (best.get("name") or "").lower()
        out["fileType"] = name.rsplit(".", 1)[-1] if "." in name else ""
        out["fileSize"] = human_size(best.get("size"))
        out["downloads"] = sum(
            int(a.get("download_count") or 0)
            for a in assets
            if ((a.get("name") or "").lower().rsplit(".", 1)[-1] in ALLOWED_EXTENSIONS)
        )
    elif include_source_zip:
        # Fallback opzionale: zip auto-generato da GitHub (solo se esplicitamente attivato)
        zip_url = release.get("zipball_url")
        if zip_url:
            out["fileUrl"] = zip_url
            out["fileType"] = "zip"
            out["fileSize"] = ""

    out["preview"] = build_preview_html(out)
    return out


# --------------------------------------------------------------------------- #
#  Main                                                                       #
# --------------------------------------------------------------------------- #

def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("Uso: python enrich_materials.py <input.json> <output.json>", file=sys.stderr)
        return 2

    in_path, out_path = Path(argv[1]), Path(argv[2])

    try:
        data = json.loads(in_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"Input non trovato: {in_path}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as e:
        print(f"JSON non valido: {e}", file=sys.stderr)
        return 2

    if not isinstance(data, list):
        print("L'input deve essere una lista JSON.", file=sys.stderr)
        return 2

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        print("[info] Nessun GITHUB_TOKEN impostato: rate limit 60 req/h.", file=sys.stderr)

    client = GitHubClient(token=token)
    include_source_zip = os.environ.get("INCLUDE_SOURCE_ZIP", "0") == "1"

    results: list[dict] = []
    total = len(data)

    for i, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            sys.stderr.write(f"[skip] item {i} non è un oggetto\n")
            continue

        try:
            enriched = enrich_one(item, client, i, include_source_zip=include_source_zip)
        except Exception as e:  # una riga rotta non ferma tutto
            sys.stderr.write(f"[error] item {i} ({item.get('title', '?')}): {e}\n")
            enriched = {
                "id": f"mat-{i:03d}",
                "title": item.get("title", ""),
                "description": item.get("description", ""),
                "category": infer_category(item.get("course", ""), item.get("category")),
                "course": item.get("course", ""),
                "year": infer_year(item.get("course", ""), item.get("year")),
                "author": item.get("author", ""),
                "date": item.get("date", ""),
                "type": (item.get("type") or "appunti").lower(),
                "fileUrl": "", "fileType": "", "fileSize": "",
                "pages": 0, "downloads": 0,
                "tags": list(item.get("tags") or []),
                "preview": "<p>Errore durante l'arricchimento.</p>",
            }

        results.append(enriched)
        status = f"{enriched['fileType']} {enriched['fileUrl']}" if enriched["fileUrl"] else "(nessun asset .pdf/.zip)"
        print(f"[{i}/{total}] {enriched['title']} → {status}")

    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nScritti {len(results)} elementi in {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))