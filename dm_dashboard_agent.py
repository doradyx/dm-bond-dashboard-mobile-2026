#!/usr/bin/env python3
"""DM interest-rate dashboard API for Scriptable.

Required env: DM_APP_KEY, DM_APP_SECRET
Run: python3 dm_dashboard_agent.py
"""
from __future__ import annotations

import json
import os
import urllib.request
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.getenv("PORT", "8787"))
APP_KEY = os.getenv("DM_APP_KEY", "")
APP_SECRET = os.getenv("DM_APP_SECRET", "")
URLS = {
    "market": "https://gapi-ext.innodealing.com/dm-mcp-service/publicapi/mcp/v1/bond-market/",
    "primary": "https://gapi-ext.innodealing.com/dm-mcp-service/publicapi/mcp/v1/bond-primary/",
    "money": "https://gapi-ext.innodealing.com/dm-mcp-service/publicapi/mcp/v1/money-market/",
}


def mcp_data(service: str, tool: str, params: dict) -> list:
    if not APP_KEY or not APP_SECRET:
        raise RuntimeError("DM_APP_KEY / DM_APP_SECRET is not configured")
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": {"params": params}}}
    request = urllib.request.Request(
        URLS[service], data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream", "x-app-key": APP_KEY, "x-app-secret": APP_SECRET},
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        raw = response.read().decode()
    # DM uses a Server-Sent Event wrapper for MCP responses.
    event_json = next((line[6:] for line in raw.splitlines() if line.startswith("data: ")), raw)
    body = json.loads(event_json)
    result = body.get("result", {})
    if result.get("isError"):
        raise RuntimeError(result["content"][0]["text"])
    text = result["content"][0]["text"]
    return json.loads(text).get("data", [])


def dashboard() -> dict:
    today = date.today()
    start = (today - timedelta(days=6)).isoformat()
    end = today.isoformat()
    message = "生成利率债、国债一级发行和最近一周资金日历面板。"

    # DM limits each curve request to about one month. Join three windows for 90 days.
    curve_start = today - timedelta(days=89)
    curve_rows = []
    window_start = curve_start
    while window_start <= today:
        window_end = min(window_start + timedelta(days=29), today)
        curve_rows += mcp_data("market", "bond_yield_curve", {
            "user_message": "查询中债国债10年期最近三个月到期收益率曲线。",
            "curve_name": "中债国债收益率曲线", "curve_term_list": ["10"],
            "curve_type": 1, "data_source": 18,
            "start_date": window_start.isoformat(), "end_date": window_end.isoformat(),
        })
        window_start = window_end + timedelta(days=1)
    ten_year = {r["valuation_date"]: r for r in curve_rows if str(r.get("curve_term")) in ("10", "10.0")}
    ten_year = [{"date": d, "yield": ten_year[d].get("yield")} for d in sorted(ten_year)]

    raw_issues = mcp_data("primary", "bond_primary_data", {"user_message": message, "start_date": start, "end_date": end, "bond_category": 2, "limit": 200})
    issues = (raw_issues[0].get("list", []) if raw_issues else [])
    issues = [r for r in issues if r.get("bond_type_desc") == "国债"]
    issues.sort(key=lambda r: r.get("subscribe_date", ""), reverse=True)

    calendar = {d: {"date": d, "omo_net": 0, "omo_items": [], "bond_issue": 0, "bond_maturity": 0, "gov_payment": 0, "gov_maturity": 0, "gov_net": 0} for d in (start, end)}
    # A date may be absent from every source; it is omitted below.
    for category, key in ((2, "omo"), (3, "bond"), (4, "gov")):
        rows = mcp_data("money", "fund_calendar", {"user_message": message, "start_date": start, "end_date": end, "data_category": category})
        for row in rows:
            d = row.get("data_date")
            if not d:
                continue
            item = calendar.setdefault(d, {"date": d, "omo_net": 0, "omo_items": [], "bond_issue": 0, "bond_maturity": 0, "gov_payment": 0, "gov_maturity": 0, "gov_net": 0})
            if key == "omo":
                item["omo_net"] += row.get("net_operation_amount") or 0
                item["omo_items"].append({"type": row.get("event_type"), "tenor": row.get("tenor"), "net": row.get("net_operation_amount")})
            elif key == "bond":
                amount = row.get("scale") or 0
                if row.get("event_type") == "发行": item["bond_issue"] += amount
                if row.get("event_type") == "到期": item["bond_maturity"] += amount
            else:
                item["gov_payment"] = row.get("gov_payment") or 0
                item["gov_maturity"] = row.get("gov_maturity_payment") or 0
                item["gov_net"] = row.get("gov_net_payment") or 0

    return {
        "as_of": today.isoformat(), "source": "DM MCP",
        "ten_year_yield_curve": ten_year,
        "treasury_issues": [{"date": r.get("subscribe_date"), "name": r.get("sec_short_name"), "tenor": r.get("bond_issue_tenor"), "amount": r.get("actu_issue_amount"), "yield": r.get("issue_yield"), "multiple": r.get("compliant_subscription_mult")} for r in issues[:5]],
        "fund_calendar": [calendar[d] for d in sorted(calendar, reverse=True)][:7],
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args): pass
    def send_json(self, status: int, data: dict):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status); self.send_header("Content-Type", "application/json; charset=utf-8"); self.send_header("Access-Control-Allow-Origin", "*"); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        if self.path == "/health": return self.send_json(200, {"status": "ok", "dm_configured": bool(APP_KEY and APP_SECRET)})
        if self.path.split("?")[0] == "/dashboard":
            try: return self.send_json(200, dashboard())
            except Exception as error: return self.send_json(503, {"error": str(error)})
        return self.send_json(404, {"error": "Use GET /dashboard or /health"})


if __name__ == "__main__":
    print(f"DM dashboard agent on :{PORT}")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
