import json, os, urllib.request
from datetime import date, timedelta

URLS={"market":"https://gapi-ext.innodealing.com/dm-mcp-service/publicapi/mcp/v1/bond-market/","primary":"https://gapi-ext.innodealing.com/dm-mcp-service/publicapi/mcp/v1/bond-primary/","money":"https://gapi-ext.innodealing.com/dm-mcp-service/publicapi/mcp/v1/money-market/"}
def call(service, tool, params):
 p=json.dumps({"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":tool,"arguments":{"params":params}}}).encode()
 r=urllib.request.Request(URLS[service],data=p,method="POST",headers={"Content-Type":"application/json","Accept":"application/json, text/event-stream","x-app-key":os.environ["DM_APP_KEY"],"x-app-secret":os.environ["DM_APP_SECRET"]})
 with urllib.request.urlopen(r,timeout=30) as x: raw=x.read().decode()
 body=json.loads(next((line[6:] for line in raw.splitlines() if line.startswith("data: ")),raw)); result=body["result"]
 if result.get("isError"): raise RuntimeError(result["content"][0]["text"])
 return json.loads(result["content"][0]["text"]).get("data",[])
today=date.today(); start=today-timedelta(days=6); curve=[]; cursor=today-timedelta(days=89)
while cursor<=today:
 end=min(cursor+timedelta(days=29),today); curve+=call("market","bond_yield_curve",{"user_message":"查询中债国债10年期最近三个月到期收益率曲线。","curve_name":"中债国债收益率曲线","curve_term_list":["10"],"curve_type":1,"data_source":18,"start_date":cursor.isoformat(),"end_date":end.isoformat()}); cursor=end+timedelta(days=1)
bydate={r["valuation_date"]:r for r in curve if str(r.get("curve_term")) in ("10","10.0")}
primary=call("primary","bond_primary_data",{"user_message":"查询最近一周国债一级发行。","start_date":start.isoformat(),"end_date":today.isoformat(),"bond_category":2,"limit":200})
issues=[r for r in (primary[0].get("list",[]) if primary else []) if r.get("bond_type_desc")=="国债"]; issues.sort(key=lambda x:x.get("subscribe_date",''),reverse=True)
cal={}
for cat,kind in ((2,"omo"),(3,"bond"),(4,"gov")):
 for r in call("money","fund_calendar",{"user_message":"查询最近一周资金日历。","start_date":start.isoformat(),"end_date":today.isoformat(),"data_category":cat}):
  x=cal.setdefault(r["data_date"],{"date":r["data_date"],"omo_net":0,"bond_issue":0,"bond_maturity":0,"gov_net":0})
  if kind=="omo": x["omo_net"]+=r.get("net_operation_amount") or 0
  elif kind=="bond": x["bond_issue" if r.get("event_type")=="发行" else "bond_maturity"]+=r.get("scale") or 0
  else: x["gov_net"]=r.get("gov_net_payment") or 0
out={"as_of":today.isoformat(),"source":"DM MCP","ten_year_yield_curve":[{"date":d,"yield":bydate[d].get("yield")} for d in sorted(bydate)],"treasury_issues":[{"date":r.get("subscribe_date"),"name":r.get("sec_short_name"),"tenor":r.get("bond_issue_tenor"),"amount":r.get("actu_issue_amount"),"yield":r.get("issue_yield")} for r in issues[:5]],"fund_calendar":sorted(cal.values(),key=lambda x:x["date"],reverse=True)[:7]}
open("data.json","w",encoding="utf-8").write(json.dumps(out,ensure_ascii=False))
