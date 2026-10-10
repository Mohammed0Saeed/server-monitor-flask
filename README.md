# server-monitor-flask
A full-screen terminal monitor for the home server, with a Flask API running underneath to track API calls.

## Run
    uv venv && uv pip install -r requirements.txt
    .venv/bin/python app.py          # full-screen TUI, Ctrl+C to quit
    .venv/bin/python app.py --plain  # scrolling console log instead (also used when not on a terminal)

Use a terminal of at least ~120x40 for the best view.

## Screen
- **Left 60%:** device & OS info, CPU / memory / storage gauges with history, temperature, battery,
  watched processes, connected devices (USB + LAN) and the live API call feed.
- **Right 40%:** animated night sky. An astronaut points at stars and the moon, which shows today's real phase.

Edit `config.json` for the port, console interval and `watch_processes` (name substrings).

## API call tracking
The Flask server listens on `config.json`'s port. Every request except the monitor's own endpoints is logged to the
API CALLS panel. Callers are tagged `AUTO` if they send an `X-Automation: <name>` header (also used as the label) or a
known automation User-Agent (curl, python-requests, n8n, ...); otherwise `WEB`. Try:

    curl -H "X-Automation: my-script" -X POST localhost:5000/api/ping
