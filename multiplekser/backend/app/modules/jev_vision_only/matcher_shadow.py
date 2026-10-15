"""Read-only reuse of the EXISTING Optima material matching logic.

No decisions, quantities or JEV Image outputs are automatically approved/exported.
"""
from __future__ import annotations
from sqlalchemy.orm import Session
from app.modules.products import Catalog
from app.modules.matcher import (
    match_against_catalog, match_against_catalog_hydraulika, rules_from_db
)

def suggest_matches(result:dict,session:Session,magazyn:str|None)->dict:
    if result.get("status")!="shadow_experimental":
        return result
    dzial=result["department"]
    catalog=Catalog.from_db(session,dzial=dzial)
    rules=rules_from_db(session) if dzial=="elektryka" else None
    for row in result["rows"]:
        name=row.get("material_candidate")
        if not name:
            row["matcher_suggestion"]=None
            continue
        if dzial=="elektryka":
            match=match_against_catalog(name,catalog,magazyn=magazyn,special_rules=rules)
        else:
            match=match_against_catalog_hydraulika(name,catalog,magazyn=magazyn)
        row["matcher_suggestion"]={
            "kod":match.kod,"name":match.nazwa,
            "quality":match.quality,"ratio":match.ratio,
            "approved":False
        }
    result["matcher_used"]=True
    result["items_approved"]=0
    return result
