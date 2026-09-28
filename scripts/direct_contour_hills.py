#!/usr/bin/env python3
"""Derive street steepness from direct intersections with official 5-ft contours.

Unlike a terrain-surface interpolation, this method only assigns a grade when a
street centerline directly crosses enough known contour elevations. This avoids
inventing elevations in complex terrain. Streets without enough direct contour
information remain unclassified rather than receiving a guessed value.
"""
from __future__ import annotations

import collections
import json
import math
import pathlib
import re
import time
import urllib.request

from shapely.geometry import LineString, MultiLineString, Point
from shapely.strtree import STRtree

ROOT = pathlib.Path(__file__).resolve().parents[1]
SITE = ROOT / "_site" / "index.html"
MANIFEST = ROOT / "_site" / "data-manifest.json"
CONTOUR_DATASET_ID = "rnbg-2qxw"
CONTOUR_URL = "https://data.sf.gov/api/v3/views/rnbg-2qxw/query.geojson?accessType=DOWNLOAD"
HEADERS = {
    "User-Agent": "sf-field-conditions-map/1.0 (+https://github.com/shreyammm/sf-field-conditions-map)",
    "Accept": "application/json, application/geo+json;q=0.9, */*;q=0.1",
}
FT_PER_M = 3.280839895
LAT0 = math.radians(37.77)
M_PER_DEG_LON = 111_320.0 * math.cos(LAT0)
M_PER_DEG_LAT = 110_540.0


def get_json(url: str, attempts: int = 3, timeout: int = 180):
    last = None
    for attempt in range(1, attempts + 1):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except Exception as exc:
            last = exc
            if attempt < attempts:
                time.sleep(2 * attempt)
    raise RuntimeError(f"Failed after {attempts} attempts: {url}\n{last}") from last


def contour_elevation(feature):
    p = feature.get("properties") or {}
    for k in ("ELEVATION", "elevation"):
        try:
            if p.get(k) not in (None, ""):
                return float(p[k])
        except (TypeError, ValueError):
            pass
    return None


def to_local(coord):
    lon, lat = float(coord[0]), float(coord[1])
    return (lon + 122.45) * M_PER_DEG_LON, (lat - 37.75) * M_PER_DEG_LAT


def local_line(coords):
    return LineString([to_local(c) for c in coords])


def parts(geometry):
    if not geometry:
        return []
    if geometry.get("type") == "LineString":
        return [geometry.get("coordinates") or []]
    if geometry.get("type") == "MultiLineString":
        return geometry.get("coordinates") or []
    return []


def extract_points(g):
    if g.is_empty:
        return []
    t = g.geom_type
    if t == "Point":
        return [g]
    if t == "MultiPoint":
        return list(g.geoms)
    if t == "GeometryCollection":
        out = []
        for x in g.geoms:
            out.extend(extract_points(x))
        return out
    # A rare overlap means the street follows a contour. This does not tell us
    # longitudinal grade, so do not convert it into a synthetic crossing.
    return []


def build_contours(fc):
    geoms, elevations = [], []
    for f in fc.get("features", []):
        z = contour_elevation(f)
        if z is None:
            continue
        for p in parts(f.get("geometry")):
            if len(p) < 2:
                continue
            try:
                g = local_line(p)
            except Exception:
                continue
            if not g.is_empty and g.length > 0:
                geoms.append(g)
                elevations.append(z)
    if len(geoms) < 10_000:
        raise ValueError(f"Too few usable contour lines: {len(geoms)}")
    return geoms, elevations, STRtree(geoms)


def crossing_grade(line, tree, contour_geoms, elevations):
    crossings = []
    for idx in tree.query(line):
        cg = contour_geoms[int(idx)]
        if not line.intersects(cg):
            continue
        inter = line.intersection(cg)
        for pt in extract_points(inter):
            s = float(line.project(pt))
            crossings.append((s, float(elevations[int(idx)])))
    if len(crossings) < 2:
        return None

    # Collapse numerical duplicates at the same along-street location/elevation.
    crossings.sort()
    clean = []
    for s, z in crossings:
        if clean and abs(s-clean[-1][0]) < 0.75 and abs(z-clean[-1][1]) < 0.25:
            continue
        clean.append((s, z))

    # Consecutive different contour elevations give exact rise/run observations.
    intervals = []
    for (s1,z1),(s2,z2) in zip(clean, clean[1:]):
        ds = s2-s1
        dz = abs(z2-z1)
        if ds < 4.0 or dz < 4.0:
            continue
        g = 100.0 * (dz / FT_PER_M) / ds
        # >45% is outside a plausible SF street running grade and usually means
        # a geometry touch/crossing artifact. Ignore that interval rather than
        # clipping it into a believable-looking value.
        if 0 <= g <= 45:
            intervals.append((ds, g, dz))
    if not intervals:
        return None

    total_span = sum(ds for ds, _g, _dz in intervals)
    if total_span < 8.0:
        return None
    weighted = sum(ds*g for ds,g,_dz in intervals) / total_span
    distinct_levels = len({z for _s,z in clean})
    if len(intervals) >= 3 and distinct_levels >= 4 and total_span >= 40:
        conf = "high"
    elif len(intervals) >= 2 and distinct_levels >= 3 and total_span >= 20:
        conf = "medium"
    else:
        conf = "low"
    return weighted, conf, len(intervals), distinct_levels, total_span


def street_grade(feature, tree, contour_geoms, elevations):
    results=[]
    for p in parts(feature.get("geometry")):
        if len(p)<2:
            continue
        line=local_line(p)
        r=crossing_grade(line,tree,contour_geoms,elevations)
        if r:
            results.append(r)
    if not results:
        return None
    # Weight multipart results by the span actually supported by contour crossings.
    span=sum(r[4] for r in results)
    g=sum(r[0]*r[4] for r in results)/span
    conf_rank={"low":1,"medium":2,"high":3}
    conf=min((r[1] for r in results), key=lambda x: conf_rank[x])
    return round(g,1),conf,sum(r[2] for r in results),max(r[3] for r in results),round(span,1)


def bucket(g):
    if g is None:return "unavailable"
    if g>=20:return "20+"
    if g>=15:return "15-19.9"
    if g>=10:return "10-14.9"
    if g>=5:return "5-9.9"
    return "<5"


def parse_payload(html):
    m=re.search(r"window\.SF_FIELD_DATA=(\{.*?\});\s*</script>",html,flags=re.S)
    if not m:raise ValueError("Embedded payload not found")
    return m,json.loads(m.group(1))


def main():
    html=SITE.read_text(encoding="utf-8")
    match,payload=parse_payload(html)
    contours=get_json(CONTOUR_URL)
    if contours.get("type")!="FeatureCollection":raise ValueError("Contour source is not GeoJSON")
    source_count=len(contours.get("features",[]))
    if not 10_000<=source_count<=20_000:raise ValueError(f"Unexpected contour feature count {source_count}")
    contour_geoms,elevations,tree=build_contours(contours)

    cats=collections.Counter(); confs=collections.Counter(); grades=[]; top=[]
    for f in payload["streets"]["features"]:
        p=f.setdefault("properties",{})
        r=street_grade(f,tree,contour_geoms,elevations)
        if r is None:
            p["estimated_grade_pct"]=None
            p["grade_confidence"]="unavailable"
            p["grade_method"]="direct_5ft_contour_crossings"
            cats["unavailable"]+=1
            continue
        g,conf,nint,nlevels,span=r
        p["estimated_grade_pct"]=g
        p["grade_confidence"]=conf
        p["grade_crossing_intervals"]=nint
        p["grade_distinct_contours"]=nlevels
        p["grade_supported_span_m"]=span
        p["grade_method"]="direct_5ft_contour_crossings"
        cats[bucket(g)]+=1; confs[conf]+=1; grades.append(g)
        top.append((g,str(p.get("street") or ""),str(p.get("st_type") or ""),str(p.get("cnn") or ""),conf,nint,span))

    graded=len(grades); total=len(payload["streets"]["features"])
    if graded<1500:
        raise ValueError(f"Direct contour coverage unexpectedly low: {graded}/{total}")
    if max(grades)>45:
        raise ValueError(f"Implausible max grade {max(grades)}")
    # Sanity guard: if an implausibly large share of classified streets are 20%+,
    # the intersection logic is likely wrong.
    if cats["20+"]>0.12*graded:
        raise ValueError(f"Too many 20%+ segments: {cats['20+']}/{graded}")

    sg=sorted(grades)
    def pct(q):return sg[min(len(sg)-1,int(q*(len(sg)-1)))]
    top.sort(reverse=True)
    meta={
        "dataset_id":CONTOUR_DATASET_ID,"source_url":CONTOUR_URL,
        "source_feature_count":source_count,"usable_contour_parts":len(contour_geoms),
        "contour_interval_ft":5,
        "method":"Directly intersect each displayed street centerline with official 5-ft contour lines. Compute rise/run only between consecutive crossings of different contour elevations; ignore implausible >45% crossing artifacts; combine supported intervals by distance. Streets without enough direct contour crossings remain unavailable.",
        "interpretation":"analytical route-planning estimate; not an official engineering street-grade survey",
        "graded_street_count":graded,"unavailable_count":total-graded,
        "confidence_counts":dict(confs),"category_counts":dict(cats),
        "distribution_pct":{"p50":pct(.5),"p75":pct(.75),"p90":pct(.9),"p95":pct(.95),"p99":pct(.99),"max":max(grades)},
        "top_20":top[:20],
    }
    pm=payload.setdefault("meta",{})
    pm["grade_source_url"]=CONTOUR_URL;pm["graded_street_count"]=graded
    pm["grade_low_confidence_count"]=confs.get("low",0)+(total-graded)
    pm["grade_category_counts"]=dict(cats);pm["grade_confidence_counts"]=dict(confs);pm["grade_method"]=meta["method"]
    packed=json.dumps(payload,ensure_ascii=False,separators=(",", ":")).replace("</","<\\/")
    SITE.write_text(html[:match.start(1)]+packed+html[match.end(1):],encoding="utf-8")
    manifest=json.loads(MANIFEST.read_text(encoding="utf-8"));manifest["hills"]=meta
    MANIFEST.write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(f"direct contour grades: {graded}/{total}; unavailable={total-graded}")
    print(f"confidence: {dict(confs)}")
    print(f"categories: {dict(cats)}")
    print(f"distribution: {meta['distribution_pct']}")
    print("top grades:")
    for row in top[:20]:print(row)

if __name__=="__main__":main()
