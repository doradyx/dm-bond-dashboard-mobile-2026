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
 end=min(cursor+timedelta(days=29),today); curve+=call("market","bond_yield_curve",{"user_message":"查询中债国债1、3、5、7、10年期最近三个月到期收益率曲线。","curve_name":"中债国债收益率曲线","curve_term_list":["1","3","5","7","10"],"curve_type":1,"data_source":18,"start_date":cursor.isoformat(),"end_date":end.isoformat()}); cursor=end+timedelta(days=1)
bydate={r["valuation_date"]:r for r in curve if str(r.get("curve_term")) in ("10","10.0")}
latest_date=max((r.get("valuation_date","") for r in curve),default="")
latest_terms={str(r.get("curve_term")).split(".")[0]:r.get("yield") for r in curve if r.get("valuation_date")==latest_date}
ten_values=[r.get("yield") for r in bydate.values() if isinstance(r.get("yield"),(int,float))]
latest_ten=bydate.get(latest_date,{}).get("yield")
ten_stats={"high":max(ten_values) if ten_values else None,"low":min(ten_values) if ten_values else None,"percentile":round(100*sum(v<=latest_ten for v in ten_values)/len(ten_values),1) if ten_values and latest_ten is not None else None}
primary=call("primary","bond_primary_data",{"user_message":"查询最近一周国债一级发行。","start_date":start.isoformat(),"end_date":today.isoformat(),"bond_category":2,"limit":200})
issues=[r for r in (primary[0].get("list",[]) if primary else []) if r.get("bond_type_desc")=="国债"]; issues.sort(key=lambda x:x.get("subscribe_date",''),reverse=True)
cal={}
for cat,kind in ((2,"omo"),(3,"bond"),(4,"gov")):
 for r in call("money","fund_calendar",{"user_message":"查询最近一周资金日历。","start_date":start.isoformat(),"end_date":today.isoformat(),"data_category":cat}):
  x=cal.setdefault(r["data_date"],{"date":r["data_date"],"omo_net":0,"bond_issue":0,"bond_maturity":0,"gov_net":0})
  if kind=="omo": x["omo_net"]+=r.get("net_operation_amount") or 0
  elif kind=="bond": x["bond_issue" if r.get("event_type")=="发行" else "bond_maturity"]+=r.get("scale") or 0
  else: x["gov_net"]=r.get("gov_net_payment") or 0
out={"as_of":today.isoformat(),"source":"DM MCP","market_snapshot":{"date":latest_date,"terms":latest_terms,"spread_10_1":(latest_terms.get("10")-latest_terms.get("1")) if isinstance(latest_terms.get("10"),(int,float)) and isinstance(latest_terms.get("1"),(int,float)) else None,"spread_10_5":(latest_terms.get("10")-latest_terms.get("5")) if isinstance(latest_terms.get("10"),(int,float)) and isinstance(latest_terms.get("5"),(int,float)) else None},"ten_year_stats":ten_stats,"ten_year_yield_curve":[{"date":d,"yield":bydate[d].get("yield")} for d in sorted(bydate)],"treasury_issues":[{"date":r.get("subscribe_date"),"name":r.get("sec_short_name"),"tenor":r.get("bond_issue_tenor"),"amount":r.get("actu_issue_amount"),"yield":r.get("issue_yield") or r.get("comprehensive_yield") or r.get("weighted_rate") or r.get("marginal_rate"),"multiple":r.get("compliant_subscription_mult")} for r in issues[:5]],"fund_calendar":sorted(cal.values(),key=lambda x:x["date"],reverse=True)[:7]}
open("data.json","w",encoding="utf-8").write(json.dumps(out,ensure_ascii=False))
