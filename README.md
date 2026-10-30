# NammaAI

A chatbot for getting around Bengaluru by Namma Metro. Ask in English, Hindi or Kannada and it finds the route, shows a line diagram and explains it.

Artificial Intelligence (BCS515B), 5th semester, VTU. Project-Based Learning, Phase 1.

| Name | USN |
|---|---|
| Haritha R | 1RF24IS037 |
| Jiya P | 1RF24IS046 |

## Idea

A general AI model will happily invent a route that doesn't exist. So here the model never calculates routes. A Python function runs Dijkstra's shortest path algorithm on our own metro data, and the model only understands the question and explains the result. If something isn't in our data, the bot says so instead of guessing.

## Features

- Fastest or fewest-changes metro route with estimated time, stops, approximate fare and a line diagram
- English, Hindi and Kannada questions, answered in the same language
- Answers about fares, which lines are open and basic rules from our own knowledge file
- Remembers the last 12 messages of a chat
- Extra metro calculators: station info, a fair meeting point for two people, monthly commute cost, stations reachable in X minutes, how far a fare budget goes, fastest vs fewest-changes comparison, nearest interchange, multi-stop trips and network statistics
- Refuses off-topic questions and says "I don't have that" for unknown stations
- Trip planner page that works without the AI
- Light/dark mode, chat export, thumbs up/down, chat delete
- Removes phone numbers, emails and ID numbers before saving
- Logs every message with time, response time and tokens

## Not included

No live data (delays, next train), no bus routes, no Pink or Blue Line (not open in October 2026), no booking, Bengaluru only.

## Tech stack

| Part | Used |
|---|---|
| Frontend | HTML, CSS, JavaScript |
| Backend | Python, FastAPI, Uvicorn |
| AI | OpenAI Python SDK (Chat Completions) pointed at Groq, Qwen model |
| Database | SQLite |
| Other | python-dotenv, heapq and difflib from the standard library |

No LangChain or LlamaIndex. The prompt, memory and tool-calling loop are our own code.

## How it works

1. `app.js` sends your message to `/api/chat`.
2. `app.py` checks it, removes personal data and loads the last 12 messages from SQLite.
3. `llm.py` builds the system prompt (persona, `knowledge.md`, scope rules, safety rules) and calls Groq.
4. If a route is needed, the model calls the `plan_route` tool and `metro.py` searches `data/metro.json`.
5. The model explains the result. The route card is built from the tool data, not the model's text.
6. `app.py` saves the reply and sends it back.

The four customization layers: persona, scope and safety rules are in `build_prompt()` in `llm.py`; custom knowledge is `knowledge.md` and `data/metro.json`.

## Tools the model can call

The model never calculates. It picks one of these Python functions (function calling) and explains the result.

| Tool | What it does |
|---|---|
| `plan_route` | Fastest or fewest-changes route with time, stops, fare |
| `list_stations` | Stations of one line |
| `station_info` | Lines, interchange status and neighbours of a station |
| `meeting_point` | Tries every station and picks the fairest meeting place for two people |
| `trip_cost` | Cost of a regular commute (fare x trips x days) |
| `reachable_within` | Stations reachable from a station in X minutes |
| `budget_reach` | How far a given fare budget goes from a station |
| `compare_routes` | Fastest and fewest-changes routes side by side |
| `nearest_interchange` | Closest interchange and how many stations away |
| `multi_stop` | Total time and fare for a trip through 3 to 5 stations |
| `network_stats` | Stations per line and interchanges, counted from the data |

Most of these reuse one Dijkstra search from a station, which gives the cost to every other station. Only the meaning of "cost" changes (minutes or number of stations).

## Files

```
app.py          server, database, privacy filter
llm.py          prompt, tool calling, Groq connection
metro.py        route finder and fare slabs
knowledge.md    knowledge the bot reads
data/metro.json lines, stations, nicknames, alerts
static/         index.html, style.css, app.js
tests/          test_set.csv, run_tests.py, verify_data.py
```

## Setup

You need Python 3.10+, Git and a free Groq key from https://console.groq.com/keys.

**Linux**
```bash
sudo apt install -y python3 python3-venv python3-pip git
git clone https://github.com/jiiya06/NAMMA-AI.git
cd NAMMA-AI
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**macOS** (after installing Homebrew)
```bash
brew install python git
git clone https://github.com/jiiya06/NAMMA-AI.git
cd NAMMA-AI
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**Windows** (install Python with "Add to PATH" ticked, and Git)
```bat
git clone https://github.com/jiiya06/NAMMA-AI.git
cd NAMMA-AI
py -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```
If PowerShell blocks activation, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` first.

**Add your key.** Create a file named `.env` in the project folder:
```
PROVIDER_ORDER=groq
GROQ_API_KEY=your_key_here
GROQ_MODEL=qwen/qwen3.8-27b
```
On Windows create it in Notepad (save as "All files"), not with PowerShell `echo`. Never share or commit this file.

**Run**
```bash
uvicorn app:app --reload
```
Open http://127.0.0.1:8000. API docs are at /docs. If port 8000 is busy, add `--port 8001`.

## Testing

With the server running, in a second terminal:
```bash
python tests/run_tests.py
```
It sends the 34 questions in `tests/test_set.csv` (routes, Hindi, Kannada, refusals, unknown stations, privacy, prompt injection) and saves results in the database. It is a keyword check, so a fail can still be a fine answer worded differently, and we read failures by hand. Usage numbers are at http://127.0.0.1:8000/api/stats.

To check the numbers without the AI or internet:
```bash
python tests/verify_data.py
```
It prints each line's station order (to compare with the BMRCL map), checks the data for mistakes, and compares the code's routes, fares and tool results with values worked out by hand (2.2 minutes per station, 5 minutes per line change, 1 station = 1 km for fares).

## Database

`chat.db` is created on first run. Tables: `sessions`, `messages` (text, latency, tokens, provider, model, time), `feedback`, `test_results`.

## Agent model (PEAS)

- Performance: correct and sourced answers, correct refusals, response time
- Environment: the Bengaluru metro network, our data and the user's messages (partially observable, one agent, discrete)
- Actuators: text replies and route cards
- Sensors: user messages, knowledge file, metro data

A goal-based agent (route finding is search) with conversation memory.

## Privacy and safety

Messages are sent to Groq, and the app says so. The privacy filter is best-effort, so please don't type personal details. The bot never asks for passwords, OTPs or payment details, and points emergencies to station staff or 112. The API key stays on the server.

## Limitations

- Station lists and interchanges were compiled by us and need checking against the BMRCL map. Verify anything important with BMRCL.
- Times are estimates (about 2.2 min per station plus 5 min per line change).
- Fares are approximate slabs. A February 2026 revision was put on hold and we couldn't confirm later changes.
- No first/last train times, since we couldn't verify them.
- We tried bus routing with a community BMTC feed but its timetables were unreliable, so we dropped it rather than show wrong answers.
- Places without a metro station (for example HSR Layout) aren't found.
- Pink and Blue line status is as of 29 October 2026.
- The model can still make mistakes, especially with Hindi and Kannada phrasing.

## Phase 2

`metro.py`, the data and `knowledge.md` don't depend on any AI provider. Only `llm.py` calls the API, so Phase 2 can replace it.

## Sources and credits

- BMRCL, https://english.bmrc.co.in (lines, network, fare rules), accessed October 2026
- News reports for network and fare status, accessed 29 October 2026: Swarajya, Business Today, Curly Tales, Deccan Herald, ThePrint, trayaan.com
- BMTC, https://mybmtc.karnataka.gov.in, for general bus information
- Vonter's bmtc-gtfs feed, https://github.com/Vonter/bmtc-gtfs, tested and not used
- OpenStreetMap contributors (ODbL), used while testing place lookups
- Groq and the Qwen team; FastAPI, Uvicorn, OpenAI Python SDK, python-dotenv, Requests
- Barlow and Noto Sans fonts via Google Fonts (SIL Open Font License)

Code, station data and knowledge file are our own work. AI tools were used as a coding and writing aid.