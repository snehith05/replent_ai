"""Repelnt gateway: serves real pages to people, decoys to scrapers.

Run:  uvicorn app.main:app --port 8000
Live dashboard (localhost only): http://localhost:8000/repelnt/dashboard
"""
from __future__ import annotations

import time
from collections import deque
from html import escape

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response

from app.content import load_page, render_page
from app.decoy import get_decoy
from app.detector import AI_CRAWLER_UAS, IntentDetector

app = FastAPI(title="Repelnt gateway", docs_url=None, redoc_url=None)
detector = IntentDetector()
REQUEST_LOG: deque[dict] = deque(maxlen=200)
LOCAL = {"127.0.0.1", "::1", "localhost"}


def _ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _log(request: Request, path: str, verdict_label: str, score: int, reasons: list[str], served: str):
    REQUEST_LOG.appendleft({
        "time": time.strftime("%H:%M:%S"),
        "ip": _ip(request),
        "path": path,
        "user_agent": request.headers.get("user-agent", ""),
        "score": score,
        "reasons": reasons,
        "verdict": verdict_label,
        "served": served,
    })


def _serve(slug: str, request: Request) -> HTMLResponse:
    source = load_page(slug)
    if source is None:
        raise HTTPException(status_code=404)

    verdict = detector.classify(_ip(request), request.headers, request.cookies)
    if verdict.poisoned:
        md, method = get_decoy(slug, source)
        served = f"poisoned ({method})"
    else:
        md, served = source, "real"

    _log(request, request.url.path, verdict.label, verdict.score, verdict.reasons, served)
    # Identical response shape either way: no header or marker reveals which path was taken.
    return HTMLResponse(render_page(md))


@app.get("/robots.txt", response_class=PlainTextResponse)
def robots() -> str:
    ai_rules = "\n".join(f"User-agent: {ua}\nDisallow: /\n" for ua in AI_CRAWLER_UAS)
    return f"{ai_rules}\nUser-agent: *\nDisallow: /trap/\n"


@app.get("/favicon.ico")
def favicon() -> Response:
    return Response(status_code=204)


@app.get("/trap/{rest:path}", response_class=HTMLResponse)
def trap(rest: str, request: Request) -> HTMLResponse:
    # Only clients that ignore robots.txt and follow hidden links end up here.
    detector.mark_trapped(detector.trap_key(_ip(request), request.headers))
    _log(request, request.url.path, "scraper", 100, ["+100 followed hidden link disallowed in robots.txt"],
         "trap page")
    return HTMLResponse(render_page("# Archive\n\nThe archive is being reorganised. "
                                    "See the [research](/research) and [survey](/survey) pages."))


def _local_only(request: Request) -> None:
    if _ip(request) not in LOCAL:
        raise HTTPException(status_code=404)


@app.get("/repelnt/log")
def log_json(request: Request) -> JSONResponse:
    _local_only(request)
    return JSONResponse(list(REQUEST_LOG))


@app.get("/repelnt/dashboard", response_class=HTMLResponse)
def dashboard(request: Request) -> HTMLResponse:
    _local_only(request)
    rows = []
    for e in REQUEST_LOG:
        poisoned = e["served"] != "real"
        rows.append(
            f'<tr class="{"bad" if poisoned else "ok"}">'
            f"<td>{e['time']}</td><td>{escape(e['path'])}</td>"
            f"<td class=ua>{escape(e['user_agent'][:70]) or '<em>(empty)</em>'}</td>"
            f"<td>{e['score']}</td><td>{escape(e['served'])}</td>"
            f"<td class=why>{'<br>'.join(escape(r) for r in e['reasons']) or '—'}</td></tr>"
        )
    real = sum(e["served"] == "real" for e in REQUEST_LOG)
    total = len(REQUEST_LOG)
    return HTMLResponse(f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta http-equiv="refresh" content="2"><title>Repelnt gateway</title>
<style>
 body {{ margin: 2rem; font: 14px/1.45 -apple-system, "Segoe UI", system-ui, sans-serif; color: #1c2b33; background: #f5f8f8; }}
 h1 {{ font-size: 1.3rem; margin: 0 0 .25rem; }}
 p {{ color: #5b707b; margin: 0 0 1.25rem; }}
 .wrap {{ overflow-x: auto; }}
 table {{ border-collapse: collapse; width: 100%; background: #fff; }}
 th, td {{ text-align: left; padding: .45rem .6rem; border-bottom: 1px solid #dde6e6; vertical-align: top; }}
 th {{ background: #e6eeee; }}
 tr.ok td:nth-child(5) {{ color: #2f6f6b; font-weight: 600; }}
 tr.bad td:nth-child(5) {{ color: #a3322a; font-weight: 600; }}
 .ua {{ max-width: 22rem; word-break: break-all; }} .why {{ color: #5b707b; font-size: 12.5px; }}
</style></head><body>
<h1>Repelnt gateway</h1>
<p>{total} recent requests: {real} got the real page, {total - real} got a decoy. Refreshes every 2 seconds.</p>
<div class="wrap"><table><tr><th>Time</th><th>Path</th><th>User-agent</th><th>Score</th><th>Served</th><th>Why</th></tr>
{''.join(rows) or '<tr><td colspan=6>No requests yet. Open the site in a browser or run scraper_demo.py.</td></tr>'}
</table></div></body></html>""")


@app.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    return _serve("index", request)


@app.get("/{slug}", response_class=HTMLResponse)
def page(slug: str, request: Request) -> HTMLResponse:
    return _serve(slug, request)
