#!/usr/bin/env python3
import argparse, csv, io, json, os, re, tempfile
from pathlib import Path
SAFE_FOLDER=re.compile(r"[A-Za-z0-9_.-]+")
IMAGES={".jpg",".jpeg",".png",".webp"}
INDEXES=("index_annotation_.csv","index_annotation_mykadfront.csv")

def remove_row(path,uuid,filename=None):
    before=path.read_bytes(); text=before.decode("utf-8-sig"); lines=text.splitlines(keepends=True)
    reader=csv.reader(io.StringIO(text,newline="")); header=next(reader); pos=header.index("uuid"); start=reader.line_num
    kept=lines[:start]; retained=[]; removed=[]
    for row in reader:
        end=reader.line_num
        if row[pos]==uuid: removed.append(dict(zip(header,row)))
        else: kept.extend(lines[start:end]); retained.append(row)
        start=end
    if len(removed)!=1: raise ValueError(f"Expected one {uuid} row in {path.name}; found {len(removed)}")
    if filename and removed[0].get("filename")!=filename: raise ValueError("Filename no longer matches capture")
    new_text="".join(kept)
    if list(csv.reader(io.StringIO(new_text,newline="")))!=[header]+retained: raise ValueError("CSV verification failed")
    after=(b"\xef\xbb\xbf" if before.startswith(b"\xef\xbb\xbf") else b"")+new_text.encode()
    return before,after,removed[0]

def atomic_write(path,data,mode):
    fd,temp=tempfile.mkstemp(prefix="."+path.name+".",suffix=".tmp",dir=path.parent)
    try:
        with os.fdopen(fd,"wb") as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.chmod(temp,mode); os.replace(temp,path)
    finally:
        try: os.unlink(temp)
        except FileNotFoundError: pass

def delete_capture(root,folder_name,uuid,filename):
    root=Path(root).resolve()
    if not SAFE_FOLDER.fullmatch(folder_name): raise ValueError("Invalid folder")
    folder=(root/folder_name).resolve()
    if folder.parent!=root or not folder.is_dir(): raise ValueError("Invalid dataset folder")
    if Path(filename).name!=filename or filename!=uuid+".jpg": raise ValueError("UUID and filename do not match")
    prepared=[]; main=None
    for name in INDEXES:
        path=folder/name
        before,after,row=remove_row(path,uuid,filename if name==INDEXES[0] else None)
        prepared.append((path,before,after,path.stat().st_mode & 0o777))
        if name==INDEXES[0]: main=row
    images=set()
    for field in ("ori_path","ocr_path"):
        if main.get(field):
            path=(folder/main[field]).resolve()
            if not path.is_relative_to(folder) or path.stem!=uuid: raise ValueError("Image path does not match selected capture")
            if path.suffix.lower() in IMAGES: images.add(path)
    for directory in (folder/"mykadfront/orig",folder/"mykadfront/crop"):
        if directory.is_dir():
            images.update(p.resolve() for p in directory.iterdir() if p.is_file() and p.stem==uuid and p.suffix.lower() in IMAGES)
    if any(not p.is_relative_to(folder) for p in images): raise ValueError("Image is outside dataset folder")
    for path,before,_,_ in prepared:
        if path.read_bytes()!=before: raise RuntimeError("Index changed during preparation")
    for path,_,after,mode in prepared: atomic_write(path,after,mode)
    deleted=[]
    for path in sorted(images):
        if path.is_file(): path.unlink(); deleted.append(str(path.relative_to(root)))
    for path,_,_,_ in prepared:
        with path.open(newline="",encoding="utf-8-sig") as stream:
            if any(row.get("uuid")==uuid for row in csv.DictReader(stream)): raise RuntimeError("Row remains")
    return {"folder":folder_name,"uuid":uuid,"filename":filename,"removed_from":list(INDEXES),"deleted_images":deleted,"json_preserved":True,"backup_created":False}

def main():
    p=argparse.ArgumentParser(description="Delete one reviewed capture from both indexes and image storage.")
    p.add_argument("--root",default="/data");p.add_argument("--folder",required=True);p.add_argument("--uuid",required=True);p.add_argument("--filename",required=True)
    a=p.parse_args(); print(json.dumps(delete_capture(a.root,a.folder,a.uuid,a.filename),indent=2))
if __name__=="__main__": main()
