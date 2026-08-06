#!/usr/bin/env python3
"""Daily check: which stores on open Jira "RSP Sync" tickets haven't synced yet,
per GCP PosApp logs, and comment the status back on the ticket.

Reuses the Jira credentials already configured for the mcp-atlassian MCP server
(read from ~/.claude.json) so no new secrets need to be created.
"""
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

GCP_PROJECT = "tdshop-prod"
LOG_NAME = "projects/tdshop-prod/logs/PosApp"
LOG_EVENT = "FetchRetailPrice"
JQL = (
    'project = SUP AND labels = PS_Front AND summary ~ "\\"RSP Sync\\"" '
    "AND statusCategory != Done ORDER BY created ASC"
)
MARKER = "Auto RSP Sync Check"

DRY_RUN = "--dry-run" in sys.argv


def load_jira_creds():
    cfg = json.loads(Path.home().joinpath(".claude.json").read_text())
    env = cfg["mcpServers"]["mcp-atlassian"]["env"]
    return env["JIRA_URL"].rstrip("/"), env["JIRA_PERSONAL_TOKEN"]


def jira_request(base_url, token, path, method="GET", body=None):
    # Uses curl (macOS system trust store) instead of urllib, whose bundled
    # certifi CA list doesn't include this org's internal CA. The token is
    # passed via a curl -K config file (mode 600), not argv, so it never
    # shows up in `ps`.
    import tempfile

    url = f"{base_url}{path}"
    with tempfile.NamedTemporaryFile("w", suffix=".curlcfg", delete=False) as cfg:
        cfg.write(f'header = "Authorization: Bearer {token}"\n')
        cfg.write('header = "Content-Type: application/json"\n')
        cfg_path = cfg.name
    Path(cfg_path).chmod(0o600)
    try:
        cmd = ["curl", "-sS", "-K", cfg_path, "-X", method, url]
        if body is not None:
            cmd += ["--data-binary", json.dumps(body)]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if proc.returncode != 0:
            raise RuntimeError(f"curl failed ({proc.returncode}): {proc.stderr.strip()}")
        return json.loads(proc.stdout) if proc.stdout.strip() else {}
    finally:
        Path(cfg_path).unlink(missing_ok=True)


def search_open_rsp_tickets(base_url, token):
    body = {
        "jql": JQL,
        "fields": ["summary", "description", "status"],
        "maxResults": 50,
    }
    result = jira_request(base_url, token, "/rest/api/2/search", "POST", body)
    return result.get("issues", [])


def parse_ticket(issue):
    desc = issue["fields"]["description"] or ""
    barcode_m = re.search(r"Oldest barcode\s*\|\s*(\d+)", desc)
    stores_m = re.search(r"Store Codes\s*\|\s*([A-Z0-9,]+)", desc)
    date_m = re.search(r"Effective Date\s*\|\s*([\d-]+)", desc)
    if not (barcode_m and stores_m and date_m):
        return None
    stores = sorted(set(stores_m.group(1).split(",")))
    return {
        "key": issue["key"],
        "summary": issue["fields"]["summary"],
        "barcode": barcode_m.group(1),
        "effective_date": date_m.group(1),
        "stores": stores,
    }


def query_synced_stores(ticket):
    store_clause = " OR ".join(f'"{s}"' for s in ticket["stores"])
    start = (
        datetime.strptime(ticket["effective_date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        - timedelta(days=1)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")
    log_filter = (
        f'resource.type="global"\n'
        f'logName="{LOG_NAME}"\n'
        f'labels.storeCode=({store_clause})\n'
        f'"{ticket["barcode"]}"\n'
        f'labels.event="{LOG_EVENT}"\n'
        f'timestamp>="{start}"\n'
    )
    proc = subprocess.run(
        [
            "gcloud", "logging", "read", log_filter,
            f"--project={GCP_PROJECT}", "--limit=2000", "--format=json",
        ],
        capture_output=True, text=True, check=True,
    )
    entries = json.loads(proc.stdout) if proc.stdout.strip() else []
    found = set()
    for e in entries:
        sc = (e.get("labels") or {}).get("storeCode")
        if sc:
            found.add(sc)
    return found


def already_reported(base_url, token, issue_key, missing):
    comments = jira_request(
        base_url, token, f"/rest/api/2/issue/{issue_key}/comment?orderBy=-created&maxResults=1"
    ).get("comments", [])
    if not comments:
        return False
    last_body = comments[0].get("body", "")
    if MARKER not in last_body:
        return False
    expected_tail = ",".join(missing) if missing else "none"
    return expected_tail in last_body


def post_comment(base_url, token, issue_key, body):
    jira_request(base_url, token, f"/rest/api/2/issue/{issue_key}/comment", "POST", {"body": body})


def format_comment(ticket, missing, found_count):
    now = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M %z")
    if missing:
        lines = [
            f"*{MARKER}* ({now})",
            f"Effective Date: {ticket['effective_date']} | Barcode: {ticket['barcode']}",
            f"Synced: {found_count}/{len(ticket['stores'])}",
            f"Not yet synced ({len(missing)}): {','.join(missing)}",
        ]
    else:
        lines = [
            f"*{MARKER}* ({now})",
            f"Effective Date: {ticket['effective_date']} | Barcode: {ticket['barcode']}",
            f"Synced: {found_count}/{len(ticket['stores'])} - all stores synced.",
        ]
    return "\n".join(lines)


def main():
    base_url, token = load_jira_creds()
    issues = search_open_rsp_tickets(base_url, token)
    if not issues:
        print("No open RSP Sync tickets found.")
        return

    for issue in issues:
        ticket = parse_ticket(issue)
        if not ticket:
            print(f"[{issue['key']}] could not parse description, skipping")
            continue

        found = query_synced_stores(ticket)
        missing = sorted(set(ticket["stores"]) - found)
        found_count = len(ticket["stores"]) - len(missing)

        print(f"[{ticket['key']}] {ticket['summary']}")
        print(f"  stores={len(ticket['stores'])} synced={found_count} missing={len(missing)} {missing}")

        comment = format_comment(ticket, missing, found_count)

        if DRY_RUN:
            print("  --- would post comment ---")
            print("  " + comment.replace("\n", "\n  "))
            continue

        if already_reported(base_url, token, ticket["key"], missing):
            print("  unchanged since last comment, skipping post")
            continue

        post_comment(base_url, token, ticket["key"], comment)
        print("  comment posted")


if __name__ == "__main__":
    main()
