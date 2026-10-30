import json, heapq, difflib
from pathlib import Path

MIN_PER_STOP = 2.2      # estimated minutes between two stations
TRANSFER_MIN = 5        # estimated minutes to change lines
KM_PER_STOP = 1         # BMRCL counts every station as 1 km for fares

DATA = json.loads((Path(__file__).parent / "data" / "metro.json").read_text(encoding="utf-8"))

lines_of = {}   # station -> set of line names it is on
nbrs = {}       # (station, line) -> neighbouring stations on that line
for lname, line in DATA["lines"].items():
    if line["status"] != "operational":
        continue
    sts = line["stations"]
    for i, s in enumerate(sts):
        lines_of.setdefault(s, set()).add(lname)
        nbrs.setdefault((s, lname), [])
        if i > 0:
            nbrs[(s, lname)].append(sts[i - 1])
        if i < len(sts) - 1:
            nbrs[(s, lname)].append(sts[i + 1])

LOWER = {n.lower(): n for n in lines_of}


def resolve(text):
    """Turn what the user typed into a station name. Returns (name, candidates)."""
    t = text.strip().lower()
    if t in DATA["aliases"]:
        return DATA["aliases"][t], []
    if t in LOWER:
        return LOWER[t], []
    hits = [n for n in lines_of if t and t in n.lower()]
    if len(hits) == 1:
        return hits[0], []
    if len(hits) > 1:
        return None, hits[:5]
    close = difflib.get_close_matches(t, list(LOWER), n=3, cutoff=0.7)
    if len(close) == 1:
        return LOWER[close[0]], []
    return None, [LOWER[c] for c in close]


def fare_for(stops):
    """Approximate fare from the number of stations travelled (2025 slabs)."""
    km = stops * KM_PER_STOP
    for limit, fare in ((2, 10), (4, 20), (6, 30), (8, 40), (10, 50), (15, 60), (20, 70), (25, 80)):
        if km <= limit:
            return fare
    return 90


def find_route(origin, destination, preference="fastest"):
    o, o_c = resolve(origin)
    d, d_c = resolve(destination)
    for name, cands, text in ((o, o_c, origin), (d, d_c, destination)):
        if not name:
            if cands:
                return {"error": f"'{text}' is not clear. Did you mean: {', '.join(cands)}?"}
            return {"error": f"I don't have a metro station or place called '{text}' in my data."}
    if o == d:
        return {"error": "Start and end are the same station."}

    # Dijkstra over (station, line) states. Changing line costs a penalty.
    penalty = 1000 if preference == "fewest_changes" else TRANSFER_MIN
    dist, prev, pq = {}, {}, []
    for ln in lines_of[o]:
        dist[(o, ln)] = 0
        heapq.heappush(pq, (0, o, ln))
    end = None
    while pq:
        cost, s, ln = heapq.heappop(pq)
        if cost > dist.get((s, ln), 1e9):
            continue
        if s == d:
            end = (s, ln)
            break
        moves = [(n, ln, MIN_PER_STOP) for n in nbrs[(s, ln)]]
        moves += [(s, other, penalty) for other in lines_of[s] if other != ln]
        for n, l2, w in moves:
            if cost + w < dist.get((n, l2), 1e9):
                dist[(n, l2)] = cost + w
                prev[(n, l2)] = (s, ln)
                heapq.heappush(pq, (cost + w, n, l2))
    if not end:
        return {"error": "No metro route found between those stations."}

    path = [end]
    while path[-1] in prev:
        path.append(prev[path[-1]])
    path.reverse()

    legs = []
    for i in range(1, len(path)):
        (s0, l0), (s1, l1) = path[i - 1], path[i]
        if s0 == s1:
            continue  # this step was only a line change
        if legs and legs[-1]["line"] == l1:
            legs[-1]["stations"].append(s1)
        else:
            legs.append({"line": l1, "stations": [s0, s1]})
    for leg in legs:
        leg["color"] = DATA["lines"][leg["line"]]["color"]
        leg["from"], leg["to"] = leg["stations"][0], leg["stations"][-1]
        leg["stops"] = len(leg["stations"]) - 1

    stops = sum(l["stops"] for l in legs)
    changes = len(legs) - 1
    return {
        "type": "journey", "origin": o, "destination": d, "preference": preference,
        "legs": legs, "total_stops": stops, "changes": changes,
        "minutes_estimated": round(stops * MIN_PER_STOP + changes * TRANSFER_MIN),
        "distance_km_estimated": stops * KM_PER_STOP,
        "fare_inr_approx": fare_for(stops), "as_of": DATA["as_of"],
        "note": "Time and distance are estimates. Fare is approximate, check the BMRCL chart.",
    }


def list_stations(line):
    for name, info in DATA["lines"].items():
        if name.lower() == line.strip().lower().replace(" line", ""):
            return {"line": name, "status": info["status"], "stations": info["stations"]}
    return {"error": f"No line called '{line}' in my data. Operating lines: Purple, Green, Yellow."}



# ---- extra tools: station info, meeting point, commute cost, reach, budget, compare, interchange, multi-stop, stats ----
def _pick(text):
    """Resolve a name, or return an error dict."""
    name, cands = resolve(text)
    if name:
        return name, None
    if cands:
        return None, {"error": f"'{text}' is not clear. Did you mean: {', '.join(cands)}?"}
    return None, {"error": f"I don't have a metro station or place called '{text}' in my data."}


def station_info(name):
    s, err = _pick(name)
    if err:
        return err
    lines = sorted(lines_of[s])
    near = sorted({n for ln in lines for n in nbrs[(s, ln)]})
    return {"station": s, "lines": lines, "is_interchange": len(lines) > 1,
            "neighbouring_stations": near, "as_of": DATA["as_of"]}


def meeting_point(a, b):
    """Try every station as a meeting place. Best = smallest longest trip, then smallest difference."""
    sa, err = _pick(a)
    if err:
        return err
    sb, err = _pick(b)
    if err:
        return err
    options = []
    for s in lines_of:
        ta = 0 if s == sa else find_route(sa, s).get("minutes_estimated")
        tb = 0 if s == sb else find_route(sb, s).get("minutes_estimated")
        if ta is None or tb is None:
            continue
        options.append((max(ta, tb), abs(ta - tb), s, ta, tb))
    options.sort()
    return {"person_a_from": sa, "person_b_from": sb, "as_of": DATA["as_of"],
            "note": "Times are estimates. Best option has the shortest trip for whoever travels longer.",
            "best_options": [{"meet_at": s, "minutes_for_a": ta, "minutes_for_b": tb} for _, _, s, ta, tb in options[:3]]}


def trip_cost(origin, destination, trips_per_day=2, days=26):
    r = find_route(origin, destination)
    if "error" in r:
        return r
    trips_per_day = max(1, min(int(trips_per_day), 10))
    days = max(1, min(int(days), 31))
    fare = r["fare_inr_approx"]
    return {"origin": r["origin"], "destination": r["destination"], "fare_per_trip_inr": fare,
            "trips_per_day": trips_per_day, "days": days, "cost_per_day_inr": fare * trips_per_day,
            "cost_total_inr": fare * trips_per_day * days, "minutes_per_trip_estimated": r["minutes_estimated"],
            "as_of": DATA["as_of"], "note": "Approximate. Based on slab fares, smart card discounts not included. Check BMRCL."}


def _spread(start, step, change):
    """Dijkstra from one station to every station. step = cost per station, change = cost per line change."""
    dist, pq = {}, []
    for ln in lines_of[start]:
        dist[(start, ln)] = 0
        heapq.heappush(pq, (0, start, ln))
    while pq:
        c, s, ln = heapq.heappop(pq)
        if c > dist.get((s, ln), 1e9):
            continue
        moves = [(n, ln, step) for n in nbrs[(s, ln)]]
        moves += [(s, o, change) for o in lines_of[s] if o != ln]
        for n, l2, w in moves:
            if c + w < dist.get((n, l2), 1e9):
                dist[(n, l2)] = c + w
                heapq.heappush(pq, (c + w, n, l2))
    best = {}
    for (s, ln), c in dist.items():
        best[s] = min(best.get(s, 1e9), c)
    return best


def reachable_within(station, minutes=20):
    s, err = _pick(station)
    if err:
        return err
    minutes = max(1, min(int(minutes), 120))
    best = _spread(s, MIN_PER_STOP, TRANSFER_MIN)
    ok = sorted((round(c), n) for n, c in best.items() if n != s and c <= minutes)
    return {"from": s, "minutes": minutes, "count": len(ok), "as_of": DATA["as_of"],
            "stations": [{"station": n, "minutes_estimated": m} for m, n in ok[:40]],
            "note": "Estimated times, no waiting time included."}


def budget_reach(station, budget_inr=30):
    s, err = _pick(station)
    if err:
        return err
    budget = int(budget_inr)
    best = _spread(s, 1, 0)
    ok = sorted((int(c), n) for n, c in best.items() if n != s and fare_for(int(c)) <= budget)
    if not ok:
        return {"from": s, "budget_inr": budget, "count": 0, "note": "Budget is below the minimum fare of 10 rupees."}
    far = max(c for c, _ in ok)
    return {"from": s, "budget_inr": budget, "count": len(ok), "as_of": DATA["as_of"],
            "max_stations_away": far, "farthest_stations": [n for c, n in ok if c == far][:6],
            "note": "Approximate slab fares. Fare depends on number of stations travelled."}


def compare_routes(a, b):
    f = find_route(a, b, "fastest")
    if "error" in f:
        return f
    c = find_route(a, b, "fewest_changes")
    keep = lambda r: {"minutes": r["minutes_estimated"], "changes": r["changes"], "stops": r["total_stops"],
                      "fare_inr": r["fare_inr_approx"], "lines": [l["line"] for l in r["legs"]]}
    return {"origin": f["origin"], "destination": f["destination"], "fastest": keep(f), "fewest_changes": keep(c),
            "same_route": keep(f) == keep(c), "as_of": DATA["as_of"]}


def nearest_interchange(station):
    s, err = _pick(station)
    if err:
        return err
    if len(lines_of[s]) > 1:
        return {"station": s, "is_interchange": True, "lines": sorted(lines_of[s])}
    best = _spread(s, 1, 0)
    hubs = sorted((int(best[n]), n) for n in lines_of if len(lines_of[n]) > 1 and n in best)
    return {"station": s, "is_interchange": False, "nearest_interchange": hubs[0][1], "stations_away": hubs[0][0],
            "all_interchanges": [{"station": n, "stations_away": d} for d, n in hubs], "as_of": DATA["as_of"]}


def multi_stop(stops):
    stops = [x for x in stops if str(x).strip()][:5]
    if len(stops) < 3:
        return {"error": "Give at least three stations in order, for example start, middle stop and end."}
    legs, mins, fare, changes = [], 0, 0, 0
    for a, b in zip(stops, stops[1:]):
        r = find_route(a, b)
        if "error" in r:
            return r
        legs.append({"from": r["origin"], "to": r["destination"], "minutes": r["minutes_estimated"], "fare_inr": r["fare_inr_approx"], "changes": r["changes"]})
        mins += r["minutes_estimated"]; fare += r["fare_inr_approx"]; changes += r["changes"]
    return {"legs": legs, "total_minutes_estimated": mins, "total_fare_inr_approx": fare, "total_changes": changes,
            "as_of": DATA["as_of"], "note": "Each leg is a separate trip, so fares are added per leg. Waiting time not included."}


def network_stats():
    per_line = {n: len(l["stations"]) for n, l in DATA["lines"].items() if l["status"] == "operational"}
    hubs = sorted(n for n in lines_of if len(lines_of[n]) > 1)
    return {"stations_per_line": per_line, "unique_stations": len(lines_of), "interchanges": hubs,
            "longest_line": max(per_line, key=per_line.get), "as_of": DATA["as_of"],
            "not_operating": [n for n, l in DATA["lines"].items() if l["status"] != "operational"]}
