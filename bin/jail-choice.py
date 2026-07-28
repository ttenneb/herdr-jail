#!/usr/bin/env python3
"""Strict action choices bound to immutable IDs and attachment fingerprints."""
import argparse, hashlib, json, re, sys
NAME = re.compile(r"yolo-[A-Za-z0-9][A-Za-z0-9_.-]*\Z"); CID = re.compile(r"[0-9a-f]{64}\Z")
WID = re.compile(r"[^\t\r\n]{1,120}\Z"); FP = re.compile(r"[0-9a-f]{64}\Z")
OPS = {"open", "close"}

def display(name):
    name = name.removeprefix("yolo-")
    return name if len(name) <= 32 else name[:23] + "…" + name[-8:]
def fingerprint(items): return hashlib.sha256(json.dumps(items, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
def valid(name, cid, attachments, fp):
    return bool(NAME.fullmatch(name) and len(name)<=114 and CID.fullmatch(cid) and attachments and
                len(attachments)<=32 and len(set(attachments)) == len(attachments) and
                attachments == sorted(attachments, key=lambda x:x.encode()) and
                all(WID.fullmatch(item) for item in attachments) and FP.fullmatch(fp) and fingerprint(attachments)==fp)
def label(op, name, attachments):
    suffix = f" (shared {len(attachments)}; affects all)" if op == "close" and len(attachments) > 1 else ""
    return ("Open " if op == "open" else "Close ") + display(name) + suffix
def emit():
    rows=[]
    for line in sys.stdin:
        fields=line.rstrip("\n").split("\t")
        if len(fields)!=6: continue
        name, directory, kind, cid, raw_attachments, fp=fields
        attachments=raw_attachments.split(",") if raw_attachments else []
        if valid(name,cid,attachments,fp): rows.append((name,directory,kind,cid,attachments,fp))
    rows.sort(key=lambda row: tuple(str(x).encode() for x in row[:4]))
    choices=[]; seen=set()
    for name, _, _, cid, attachments, fp in rows:
        for op in ("open","close"):
            identifier=f"{op}:{cid}"
            if identifier in seen: continue
            seen.add(identifier)
            choices.append({"id":identifier,"label":label(op,name,attachments),"payload":{"operation":op,"container":{"name":name,"id":cid,"attachments":attachments,"attachment_fingerprint":fp}}})
            if len(choices)==64: break
        if len(choices)==64: break
    print(json.dumps({"version":1,"choices":choices},separators=(",",":"),ensure_ascii=False))
def pairs(items):
    result={}
    for key,value in items:
        if key in result: raise ValueError("duplicate JSON key")
        result[key]=value
    return result
def parse():
    try: value=json.load(sys.stdin,object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(ValueError()))
    except Exception as error: print(f"invalid choice JSON: {error}",file=sys.stderr); return 1
    try:
        if not isinstance(value,dict) or set(value)!={"id","label","payload"}: raise ValueError()
        payload=value["payload"]
        if not isinstance(payload,dict) or set(payload)!={"operation","container"}: raise ValueError()
        op=payload["operation"]; container=payload["container"]
        if op not in OPS or not isinstance(container,dict) or set(container)!={"name","id","attachments","attachment_fingerprint"}: raise ValueError()
        name,cid,attachments,fp=container["name"],container["id"],container["attachments"],container["attachment_fingerprint"]
        if not isinstance(attachments,list) or not all(isinstance(x,str) for x in attachments) or not valid(name,cid,attachments,fp): raise ValueError()
        if value["id"] != f"{op}:{cid}" or value["label"] != label(op,name,attachments): raise ValueError()
    except (KeyError,ValueError,TypeError): print("choice identity does not match its payload",file=sys.stderr); return 1
    print("\t".join((op,name,cid,",".join(attachments),fp))); return 0
def main():
    mode=argparse.ArgumentParser(); mode.add_argument("mode",choices=("emit","parse")); args=mode.parse_args()
    return emit() if args.mode=="emit" else parse()
if __name__=="__main__": raise SystemExit(main())
