"""Synthetic 90-day scenario. EXPECTED RESULT (written before running):
  1. All 90 days land in their EVENT days even though every row was ingested at NOW.
  2. Engine panel covers ~90 active days (not 1).
  3. The planted effect sleep_duration -> focus (lag 1) is found at tier >= ERL-2; reported as
     candidate_association/validated_finding, never as causal.
  4. 'stress' and 'steps' share only a weekly cycle: any link between them must NOT reach the report
     at ERL-2+ (spurious, should be removed by weekly-cycle adjustment).
  5. A different user's candidate never enters the report; weekly findings stay descriptive.
"""
import json, sys, time
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.dirname(__import__('os').path.abspath(__file__))))
import numpy as np
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS
from backend.app import research as nre
from backend.app.weekly import build_weekly_report

NOW=datetime(2026,10,25,12,0,tzinfo=timezone.utc); rng=np.random.default_rng(7)
T=90; days=np.arange(T)
wk=np.sin(2*np.pi*days/7)
sleep=7+0.6*rng.standard_normal(T)+0.4*wk
focus=np.empty(T); focus[0]=6
for t in range(1,T): focus[t]=6+0.9*(sleep[t-1]-7)+0.5*rng.standard_normal()
stress=5+1.2*wk+0.4*rng.standard_normal(T)
steps=6+1.1*wk+0.4*rng.standard_normal(T)
recs=[]
for i in range(T):
    when=NOW-timedelta(days=T-1-i)
    for k,v in (("sleep_duration",sleep[i]),("focus",np.clip(focus[i],0,10)),("stress",np.clip(stress[i],0,10)),("energy",np.clip(steps[i],0,10))):
        recs.append(NS(kind=k,value_numeric=float(v),value_text=None,observed_at=when.replace(hour=9),recorded_at=NOW))
print("rows:",len(recs),"| all ingested at one instant:",len({r.recorded_at for r in recs})==1)

panel=nre.build_panel(recs,tz="Africa/Lagos",end=NOW,window_days=90)
active=int(panel.any_observed_mask().sum()); print("engine panel active days:",active,"of",panel.T)
t0=time.time(); res=nre.analyze_panel(panel,nre.EngineConfig(window_days=90)); print(f"engine analyze_panel took {time.time()-t0:.1f}s; candidates={len(res.candidates)}")
cands=[]
for c in res.candidates:
    lvl=c["tier"]["level"]; ex,out=c["id"].split("->")[0], c["id"].split("->")[1].split("@")[0]
    cands.append(dict(user_id=1,hypothesis_id=c["id"],exposure=ex,outcome=out,lag=int(c["id"].split("@")[1]),status={0:"INCONCLUSIVE",1:"TESTING",2:"SUPPORTED",3:"SUPPORTED",4:"CONFIRMED",5:"CONFIRMED"}[lvl],
        evidence_tier=c["tier"]["code"],evidence_label=c["tier"]["label"],q_value=None,n_pairs=None,effect_estimate=None,confidence=None,model_version=nre.MODEL_VERSION,last_tested_at=NOW.isoformat(),echo_of=c.get("echo_of")))
print("tiers by pair:")
for c in sorted(cands,key=lambda x:-int(x["evidence_tier"][-1]))[:8]: print("  ",c["hypothesis_id"],c["evidence_tier"],c["status"])
foreign=dict(cands[0],user_id=2,hypothesis_id="foreign:sleep->focus@1")
run=dict(id=1,status="completed",created_at=NOW-timedelta(minutes=5),model_version=nre.MODEL_VERSION,summary={"engine":f"{nre.ENGINE_NAME} v{nre.ENGINE_VERSION}","window_days":90})
rep=build_weekly_report(recs,user_id=1,tz_name="Africa/Lagos",now=NOW,engine_run=run,engine_candidates=cands+[foreign],newest_ingested_at=NOW-timedelta(minutes=10),current_model_version=nre.MODEL_VERSION)
print("\nREPORT status/state:",rep["status"],rep["report_state"],"| engine:",rep["engine"]["state"],"| excluded:",rep["engine"]["excluded"])
print("coverage:",{k:rep["coverage"][k] for k in ("days","observations","baseline_days")})
for f in rep["findings"]: print(f"  [{f['type']}] {f['title']}  <- {f['evidence'].get('hypothesis_id') or f['evidence'].get('kind')}")
spur=[f for f in rep["findings"] if f["type"]!="descriptive_summary" and {"stress","energy"}=={f["evidence"]["hypothesis_id"].split("->")[0], f["evidence"]["hypothesis_id"].split("->")[1].split("@")[0]}]
print("\nCHECKS")
print(" 1 event-day coverage (7 week days, 21 baseline days):", rep["coverage"]["days"]==7 and rep["coverage"]["baseline_days"]==21)
print(" 2 engine panel active days == 90:", active==90)
print(" 3 planted sleep->focus reported as association/validated:", any(f["evidence"].get("hypothesis_id","").startswith("sleep_duration->focus") for f in rep["findings"] if f["type"] in("candidate_association","validated_finding")))
print(" 4 spurious stress<->energy NOT reported as association:", not spur)
print(" 5 foreign user's candidate excluded:", rep["engine"]["excluded"].get("unauthorised")==1 and not any("foreign" in f["id"] for f in rep["findings"]))
import re
def _asserts_cause(body):
    b=re.sub(r"(does not|doesn't|do not|not) (show|establish|imply)[^.]*\.", "", body.lower())
    return any(w in b for w in ("causes","caused by","because of","leads to","results in"))
print(" 6 no non-negated causal assertion in any finding:", not any(_asserts_cause(f["body"]) for f in rep["findings"]))
