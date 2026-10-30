# Proof checks. No AI and no internet needed.
# Part 1 prints the station order so you can compare it with the BMRCL map.
# Part 2 checks the data for mistakes.
# Part 3 compares the code's answers with numbers worked out by hand.
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import metro

ok = bad = 0


def check(name, got, want):
    global ok, bad
    if got == want:
        ok += 1
        print("PASS", name, "->", got)
    else:
        bad += 1
        print("FAIL", name, "-> got", got, "but expected", want)


print("PART 1: station order (compare with https://english.bmrc.co.in)")
for lname, line in metro.DATA["lines"].items():
    if line["status"] == "operational":
        print(f"\n{lname} Line, {len(line['stations'])} stations")
        for i, s in enumerate(line["stations"], 1):
            print(f"  {i:2}. {s}")

print("\nPART 2: data checks")
for lname, line in metro.DATA["lines"].items():
    st = line["stations"]
    check(lname + " has no duplicate stations", len(st) == len(set(st)), True)
check("interchanges", sorted(n for n in metro.lines_of if len(metro.lines_of[n]) > 1), ["Majestic", "RV Road"])
check("unique stations", len(metro.lines_of), 83)
for alias, target in metro.DATA["aliases"].items():
    check("alias '" + alias + "' points to a real station", target in metro.lines_of, True)

print("\nPART 3: code against hand calculation (2.2 min per station, 5 min per change, 1 station = 1 km)")
r = metro.find_route("Indiranagar", "Majestic")
check("Indiranagar to Majestic: stops, minutes, fare", (r["total_stops"], r["minutes_estimated"], r["fare_inr_approx"]), (7, 15, 40))
r = metro.find_route("Whitefield", "Majestic")
check("Whitefield to Majestic", (r["total_stops"], r["minutes_estimated"], r["fare_inr_approx"]), (22, 48, 80))
r = metro.find_route("Silk Board", "Majestic")
check("Silk Board to Majestic", (r["total_stops"], r["changes"], r["minutes_estimated"], r["fare_inr_approx"]), (11, 1, 29, 60))
r = metro.find_route("Majestic", "Banashankari")
check("Majestic to Banashankari", (r["total_stops"], r["minutes_estimated"]), (8, 18))
r = metro.find_route("Bommasandra", "Majestic")
check("Bommasandra to Majestic", (r["total_stops"], r["changes"], r["minutes_estimated"]), (22, 1, 53))
check("fare slabs 1, 7, 12, 30 stations", [metro.fare_for(n) for n in (1, 7, 12, 30)], [10, 40, 60, 90])
check("unknown place gives an error", "error" in metro.find_route("Atlantis", "Majestic"), True)
check("Pink Line is not in the route finder", "error" in metro.list_stations("Pink") or metro.list_stations("Pink").get("status") != "operational", True)

si = metro.station_info("Majestic")
check("Majestic lines", (si["lines"], si["is_interchange"]), (["Green", "Purple"], True))
check("trip cost 2 trips x 26 days", metro.trip_cost("Indiranagar", "Majestic", 2, 26)["cost_total_inr"], 40 * 2 * 26)
m = metro.meeting_point("Indiranagar", "Banashankari")
check("meeting point gives 3 options", len(m["best_options"]), 3)
check("Vidhana Soudha reachable from Majestic in 20 min", "Vidhana Soudha" in [x["station"] for x in metro.reachable_within("Majestic", 20)["stations"]], True)
check("Indiranagar with 30 rupees: stations away", metro.budget_reach("Indiranagar", 30)["max_stations_away"], 6)
ni = metro.nearest_interchange("Hoodi")
check("nearest interchange to Hoodi", (ni["nearest_interchange"], ni["stations_away"]), ("Majestic", 14))
ms = metro.multi_stop(["Indiranagar", "Majestic", "Banashankari", "Silk Board"])
check("multi stop minutes, fare, changes", (ms["total_minutes_estimated"], ms["total_fare_inr_approx"], ms["total_changes"]), (49, 110, 1))
check("compare routes Silk Board to Majestic", metro.compare_routes("Silk Board", "Majestic")["same_route"], True)
ns = metro.network_stats()
check("stations per line", ns["stations_per_line"], {"Purple": 37, "Green": 32, "Yellow": 16})

print(f"\n{ok} passed, {bad} failed")
