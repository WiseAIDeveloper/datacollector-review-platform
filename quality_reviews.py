"""Persistent quality reviews, independent of annotation and deletion decisions."""
import json
from datetime import datetime,timezone
from pathlib import Path
from delete_capture import atomic_write
from edit_capture import Conflict, edit_capture
from delete_capture import INDEXES

def read_reviews(path):
    path=Path(path)
    return json.loads(path.read_text()) if path.exists() else {}

def save_review(path, row, status, notes, expected, root):
    if status not in {'pass','error','unreviewed'}:raise ValueError('Invalid quality status')
    if not isinstance(notes,str) or len(notes)>4096:raise ValueError('Notes must be at most 4096 characters')
    reviews=read_reviews(path);key=row['key']
    if reviews.get(key)!=expected:raise Conflict('Quality review changed; refresh before saving')
    entry=dict(key=key,folder=row['folder'],uuid=row['metadata']['uuid'],filename=row['metadata']['filename'],status=status,notes=notes,reviewed_at=datetime.now(timezone.utc).isoformat())
    reviews[key]=entry
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    folder=Path(root)/row['folder']
    originals=[(folder/name,(folder/name).read_bytes(),(folder/name).stat().st_mode&0o777) for name in INDEXES]
    value={'pass':'pass','error':'fail','unreviewed':''}[status]
    edit_capture(root,row['folder'],row['metadata']['uuid'],row['metadata']['filename'],{'quality_review_status':value},row['metadata'],allowed_fields={'quality_review_status'})
    try:
        atomic_write(path,(json.dumps(reviews,indent=2,ensure_ascii=False)+'\n').encode(),0o644)
    except Exception:
        for index,content,mode in originals:atomic_write(index,content,mode)
        raise
    return entry
