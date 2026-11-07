"""
Shared helpers for Wikidata / Wikipedia / Overpass access (polite, cached, retrying).
Every value returned here comes straight from the public APIs; nothing is derived
by guesswork. A small on-disk JSON cache makes the pipeline resumable.
"""
import json
import os
import re
import time
import unicodedata
from datetime import date

import requests

UA = "LiveIQ-DataBot/1.0 (internal Zomato District analytics; jash.doshi@zomato.com)"
WD_API = "https://www.wikidata.org/w/api.php"
WD_SPARQL = "https://query.wikidata.org/sparql"
S = requests.Session()
S.headers.update({"User-Agent": UA, "Accept": "application/json"})
CACHE_DIR = os.environ.get("LIVEIQ_CACHE", "/private/tmp/claude-501/-Users-jash-doshi-zomato-com-Desktop-event/9552e9da-2773-47bc-b57e-03c883fcc8dc/scratchpad/cache")
os.makedirs(CACHE_DIR, exist_ok=True)
TODAY = date.today().isoformat()
_last = [0.0]


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = s.replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"^the ", "", s.strip())
    return s.strip()


def get(url, params=None, min_gap=0.35, tries=5, timeout=60):
    for i in range(tries):
        wait = min_gap - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()
        try:
            r = S.get(url, params=params, timeout=timeout)
        except requests.RequestException:
            time.sleep(2 * (i + 1))
            continue
        if r.status_code == 200:
            return r
        if r.status_code in (429, 503, 504, 502):
            time.sleep(int(r.headers.get("Retry-After", 5 * (i + 1))))
            continue
        if r.status_code == 404:
            return None
        time.sleep(2 * (i + 1))
    return None


def _cache_path(name):
    return os.path.join(CACHE_DIR, name + ".json")


def cached(name, fn):
    p = _cache_path(name)
    if os.path.exists(p):
        return json.load(open(p))
    v = fn()
    json.dump(v, open(p, "w"))
    return v


def search(term, limit=8, lang="en"):
    r = get(WD_API, dict(action="wbsearchentities", search=term, language=lang, uselang=lang,
                         type="item", limit=limit, format="json"))
    return [x["id"] for x in (r.json().get("search", []) if r else [])]


def get_entities(qids, props="claims|labels|aliases|sitelinks|descriptions"):
    """Batch-fetch (50/call), cached per QID."""
    out, todo = {}, []
    for q in qids:
        p = _cache_path("Q_" + q)
        if os.path.exists(p):
            out[q] = json.load(open(p))
        else:
            todo.append(q)
    for i in range(0, len(todo), 50):
        chunk = todo[i:i + 50]
        r = get(WD_API, dict(action="wbgetentities", ids="|".join(chunk), props=props,
                             languages="en", sitefilter="enwiki", format="json"))
        if not r:
            continue
        for q, e in r.json().get("entities", {}).items():
            if "missing" in e:
                continue
            slim = {
                "label": e.get("labels", {}).get("en", {}).get("value"),
                "desc": e.get("descriptions", {}).get("en", {}).get("value"),
                "aliases": [a["value"] for a in e.get("aliases", {}).get("en", [])],
                "enwiki": e.get("sitelinks", {}).get("enwiki", {}).get("title"),
                "claims": {},
            }
            # total sitelinks count requires unfiltered fetch; approximate via separate call below
            for pid, cl in e.get("claims", {}).items():
                vals = []
                for c in cl:
                    if c.get("rank") == "deprecated":
                        continue
                    sn = c.get("mainsnak", {})
                    if sn.get("snaktype") != "value":
                        continue
                    dv = sn["datavalue"]["value"]
                    if isinstance(dv, dict) and "id" in dv:
                        vals.append(dv["id"])
                    elif isinstance(dv, dict) and "latitude" in dv:
                        vals.append([dv["latitude"], dv["longitude"]])
                    elif isinstance(dv, dict) and "amount" in dv:
                        q_ = c.get("qualifiers", {}).get("P585", [])
                        t = q_[0]["datavalue"]["value"]["time"][1:5] if q_ and q_[0].get("datavalue") else None
                        vals.append({"amount": float(dv["amount"]), "year": t})
                    else:
                        vals.append(dv)
                if vals:
                    slim["claims"][pid] = vals
            out[q] = slim
            json.dump(slim, open(_cache_path("Q_" + q), "w"))
    return out


def sitelink_counts(qids):
    out = {}
    for i in range(0, len(qids), 50):
        chunk = qids[i:i + 50]
        r = get(WD_API, dict(action="wbgetentities", ids="|".join(chunk), props="sitelinks", format="json"))
        if r:
            for q, e in r.json().get("entities", {}).items():
                out[q] = len(e.get("sitelinks", {}))
    return out


def labels(qids):
    out = {}
    qids = list(dict.fromkeys(qids))
    ents = get_entities(qids, props="labels|claims|sitelinks")
    for q, e in ents.items():
        out[q] = e["label"]
    return out


def sparql(query, name=None):
    def run():
        r = get(WD_SPARQL, {"query": query, "format": "json"}, min_gap=1.5, timeout=120)
        if r is None:
            raise RuntimeError("SPARQL failed")
        return r.json()["results"]["bindings"]
    return cached("sparql_" + name, run) if name else run()


def wp_summary(title):
    r = get("https://en.wikipedia.org/api/rest_v1/page/summary/" + requests.utils.quote(title.replace(" ", "_"), safe=""), min_gap=0.2)
    if not r:
        return None
    j = r.json()
    if j.get("type") == "disambiguation":
        return None
    return {"extract": j.get("extract"), "title": j.get("title"), "url": j.get("content_urls", {}).get("desktop", {}).get("page")}


def commons_thumb(filename, width=480):
    return "https://commons.wikimedia.org/wiki/Special:FilePath/" + requests.utils.quote(filename.replace(" ", "_")) + f"?width={width}"
