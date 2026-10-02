"""Is Laya working? Its own README example, plus questions whose answer is in the text."""

import json

import modal

from scripts.modal_laya import Laya, app

README_STATE = "Hi, we were billed twice for March. Please refund the duplicate today or we will cancel our plan."
README_Q = {
    "department": {"type": "choice", "instructions": "Which department should handle this?",
                   "criteria": {"billing": "invoices, payments, refunds", "technical": "bugs, outages, system errors", "other": "everything else"}},
    "churn_risk": {"type": "noul", "instructions": "Does the user threaten to cancel or leave?"},
}
IN_TEXT = [
    ("The point is in the middle of the Pacific Ocean, 2,000 km from the nearest island.", "expect Water"),
    ("The point is in the Sahara desert, in southern Algeria.", "expect Land"),
    ("Our office is in Nairobi, Kenya.", "expect Africa"),
    ("Our office is in Lima, Peru.", "expect South America"),
]
LAND_Q = {"lw": {"type": "choice", "instructions": "Is this location over land or over water?", "criteria": {"Land": None, "Water": None}},
          "cont": {"type": "choice", "instructions": "Which continent is this?",
                   "criteria": {c: None for c in ["Africa", "Antarctica", "Asia", "Europe", "North America", "Oceania", "South America"]}}}

if __name__ == "__main__":
    with app.run():
        for ck in ["typed-decisions", "english", "multilingual"]:
            m = Laya(checkpoint=ck)
            r = m.one_each.remote([(README_STATE, README_Q)])[0]["answers"]
            print(f"\n== {ck}\nREADME: department={r['department']['choice']} {r['department']['probabilities']}  churn_risk={r['churn_risk']['noul']}")
            res = m.one_each.remote([(s, LAND_Q) for s, _ in IN_TEXT])
            for (s, exp), rr in zip(IN_TEXT, res):
                a = rr["answers"]
                print(f"  {exp:22} land/water={a['lw']['choice']} ({a['lw']['probabilities']['Land']:.2f})  continent={a['cont']['choice']} ({max(a['cont']['probabilities'].values()):.2f})  | {s[:45]}")
