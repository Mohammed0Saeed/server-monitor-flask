# server-monitor-flask
A server monitor to show the stats of the home server for personal use and management

## Run
    uv venv && uv pip install -r requirements.txt
    .venv/bin/python app.py      # dashboard on http://localhost:5000

Edit `config.json` to change the port, console banner interval, and `watch_processes` (name substrings).

## API call tracking
Every request except the dashboard's own polling is logged to the console and the dashboard feed.
Callers are tagged `AUTO` if they send an `X-Automation: <name>` header (also used as the label) or a
known automation User-Agent (curl, python-requests, n8n, ...); otherwise `WEB`. Try:

    curl -H "X-Automation: my-script" -X POST localhost:5000/api/ping
