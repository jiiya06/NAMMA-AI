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
