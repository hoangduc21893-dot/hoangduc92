#!/usr/bin/env python3
"""Read-only VN30F Actions health report. No trading logic or orders."""
import json
import os
import sys
from datetime import datetime, timedelta, time
from urllib import request, error
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Ho_Chi_Minh")
REPO = "hoangduc21893-dot/hoangduc92"
WORKFLOW = "vn30f1m_watch.yml"

def session(t):
    return t.weekday() < 5 and (time(8,45) <= t.time() <= time(11,30) or time(13,0) <= t.time() <= time(14,45))

def summarize(runs, day):
    relevant = []
    for r in runs:
        if r.get("event") != "schedule":
            continue
        try:
            dt = datetime.fromisoformat(r["created_at"].replace("Z", "+00:00")).astimezone(TZ)
        except (KeyError, ValueError, TypeError):
            continue
        if dt.date() == day and session(dt):
            relevant.append((dt, r))
    relevant.sort(key=lambda x: x[0])
    ok = sum(r.get("conclusion") == "success" for _,r in relevant)
    failed = sum(r.get("conclusion") in ("failure","timed_out","cancelled","action_required") for _,r in relevant)
    gaps = [round((b[0]-a[0]).total_seconds()/60,1) for a,b in zip(relevant,relevant[1:])]
    return {"date":day.isoformat(),"runs":len(relevant),"success":ok,"failed_or_cancelled":failed,
            "pending":len(relevant)-ok-failed,"max_gap_minutes":max(gaps,default=None),
            "last_run":relevant[-1][0].strftime("%H:%M") if relevant else None}

def render(s, data_error=None):
    if data_error:
        status="UNKNOWN"
    elif s["runs"] == 0 or s["failed_or_cancelled"] or s["pending"] or (s["max_gap_minutes"] is not None and s["max_gap_minutes"] > 15):
        status="WARN"
    else:
        status="OK (run-level only)"
    gap = "N/A" if s["max_gap_minutes"] is None else str(s["max_gap_minutes"])
    return ("VN30F SYSTEM HEALTH | "+s["date"]+" (VN)\n"
            "Status: "+status+"\n"
            "Scheduled in-session runs: "+str(s["runs"])+"\n"
            "Success: "+str(s["success"])+" | Failed/cancelled: "+str(s["failed_or_cancelled"])+" | Pending: "+str(s["pending"])+"\n"
            "Largest observed gap: "+gap+" min | Last run: "+str(s["last_run"] or "N/A")+"\n"
            "Signals: NOT AUDITED | Telegram trade alerts: NOT AUDITED\n"
            "Note: GitHub run success does not prove data freshness, strategy signals or alert delivery."
            + ("\nGitHub API: "+data_error if data_error else ""))

def fetch_runs(token):
    url = "https://api.github.com/repos/"+REPO+"/actions/workflows/"+WORKFLOW+"/runs?per_page=100"
    headers={"Accept":"application/vnd.github+json","User-Agent":"vn30f-health"}
    if token: headers["Authorization"]="Bearer "+token
    req=request.Request(url,headers=headers)
    with request.urlopen(req,timeout=20) as response:
        return json.load(response).get("workflow_runs",[])

def send_telegram(message, token, chat_id):
    if not token or not chat_id:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")
    payload=json.dumps({"chat_id":chat_id,"text":message}).encode()
    req=request.Request("https://api.telegram.org/bot"+token+"/sendMessage",data=payload,
                        headers={"Content-Type":"application/json"},method="POST")
    try:
        with request.urlopen(req,timeout=20) as response:
            body=json.load(response)
        if body.get("ok") is not True:
            raise RuntimeError("Telegram response ok=false")
    except error.HTTPError as exc:
        raise RuntimeError("Telegram HTTP status "+str(exc.code)) from None

def main():
    now=datetime.now(TZ)
    # Scheduled 15:15 VN; manual runs report today's activity so far.
    day=now.date()
    try:
        runs=fetch_runs(os.getenv("GITHUB_TOKEN",""))
        summary=summarize(runs,day)
        message=render(summary)
    except Exception as exc:
        summary=summarize([],day)
        message=render(summary,type(exc).__name__)
    print(message)
    os.makedirs("data",exist_ok=True)
    with open("data/vn30f_health_report.json","w",encoding="utf-8") as f:
        json.dump({"summary":summary,"message":message,"generated_at":now.isoformat()},f,ensure_ascii=False,indent=2)
    try:
        send_telegram(message,os.getenv("TELEGRAM_BOT_TOKEN"),os.getenv("TELEGRAM_CHAT_ID"))
    except Exception as exc:
        print("Telegram health delivery FAILED:",type(exc).__name__,file=sys.stderr)
        return 1
    print("Telegram health delivery ACKNOWLEDGED")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
