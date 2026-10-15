"""Bounded TypeSafe JEV 1.14 Image requests. No second AI provider."""
from __future__ import annotations
import json,os,time,uuid
from dataclasses import dataclass
from typing import Any
import httpx

API_URL="https://api.typesafe.ai/v1/systemone"
MODEL="jev-1.14.0"

class JevVisionError(RuntimeError): pass

@dataclass(frozen=True)
class ImageQuestion:
    key:str
    image:bytes
    prompt:str
    criteria:dict[str,str]

@dataclass(frozen=True)
class ImageAnswer:
    choice:str|None
    confidence:float|None
    duration_ms:int
    tokens_in:int

def ask_images(questions:list[ImageQuestion],timeout:float=18.0,
               client:httpx.Client|None=None)->dict[str,ImageAnswer]:
    if not questions or len(questions)>24:
        raise JevVisionError("request must contain 1..24 questions")
    api_key=os.getenv("TYPESAFE_API_KEY")
    if not api_key:raise JevVisionError("TYPESAFE_API_KEY not configured")
    assets={};state={"cells":[]};q={};files={}
    for i,question in enumerate(questions):
        if not question.key or question.key in q or not question.criteria:
            raise JevVisionError("invalid/duplicate question")
        if not 500<len(question.image)<5_000_000:
            raise JevVisionError("image too small or too large")
        ref="ref-"+str(uuid.uuid4());part=f"photo_{i}"
        assets[ref]={"type":"image","part":part}
        state["cells"].append({"key":question.key,"image":ref})
        files[part]=(f"cell_{i}.png",question.image,"image/png")
        q[question.key]={"type":"choice",
             "instructions":question.prompt+" Look ONLY at `cells["+str(i)+"].image`.",
             "criteria":question.criteria}
    body={"model":MODEL,"state":state,"assets":assets,"questions":q}
    files={"request":(None,json.dumps(body,ensure_ascii=False),"application/json"),**files}
    start=time.monotonic()
    def send(h:httpx.Client):
        return h.post(API_URL,headers={"Authorization":"Bearer "+api_key,
                        "TypeSafe-Danger-Zone-Images":"true"},
                      files=files,timeout=timeout)
    try:
        if client is None:
            with httpx.Client() as cli:resp=send(cli)
        else:resp=send(client)
    except httpx.HTTPError as exc:
        raise JevVisionError("JEV Image transport "+type(exc).__name__) from exc
    elapsed=round((time.monotonic()-start)*1000)
    if resp.status_code!=200:
        raise JevVisionError("JEV Image HTTP "+str(resp.status_code))
    try:data=resp.json()
    except ValueError as exc:raise JevVisionError("invalid JSON response") from exc
    answers=data.get("answers")
    if not isinstance(answers,dict):
        raise JevVisionError("no answers")
    token=int((data.get("usage") or {}).get("input_tokens") or 0)
    out={}
    for question in questions:
        a=answers.get(question.key)
        choice=a.get("choice") if isinstance(a,dict) else None
        if choice not in question.criteria:choice=None
        raw=a.get("confidence") if isinstance(a,dict) else None
        try:conf=float(raw) if raw is not None else None
        except (TypeError,ValueError):conf=None
        if conf is not None and not 0<=conf<=1:conf=None
        out[question.key]=ImageAnswer(choice,conf,elapsed,token)
    return out
