from fastapi import APIRouter, Depends, File, UploadFile, HTTPException
from sqlalchemy.orm import Session
from ..deps import get_current_user
from ..db.models import User, Note, MemoryItem
from ..db.session import get_db
from ..ingest.loader import load_text, split_text
from ..vector_store.factory import get_notes_store, delete_note_vectors
import uuid

router = APIRouter(prefix="/notes", tags=["notes"])

@router.post("/upload")
async def upload_note(file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not file.filename or file.filename.lower().split(".")[-1] not in {"md", "txt", "pdf", "docx"}:
        raise HTTPException(400, "unsupported file type")
    content = load_text(file.filename, await file.read())
    doc_id = f"u{user.id}_{uuid.uuid4().hex}"
    chunks = split_text(content)
    # 用可预测的 keys：每个 chunk 的 key 为 {doc_id}_c{i}，
    # 这样删除笔记时能按 doc_id 精确定位并清理向量。
    keys = [f"{doc_id}_c{i}" for i in range(len(chunks))]
    get_notes_store(user.id).add_texts(
        chunks,
        metadatas=[{"user_id": user.id, "doc_id": doc_id, "filename": file.filename} for _ in chunks],
        keys=keys,
    )
    db.add(Note(user_id=user.id, doc_id=doc_id, filename=file.filename, content=content)); db.commit()
    return {"doc_id": doc_id, "filename": file.filename, "chunks": len(chunks)}

@router.get("/stats")
def stats(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    note_count = db.query(Note).filter(Note.user_id == user.id).count()
    memory_count = db.query(MemoryItem).filter(MemoryItem.user_id == user.id).count()
    last = db.query(Note).filter(Note.user_id == user.id).order_by(Note.id.desc()).first()
    return {
        "note_count": note_count,
        "memory_count": memory_count,
        "last_upload": last.created_at.isoformat() if last and last.created_at else "",
        "user": user.email,
    }

@router.get("/search")
def search_notes(q: str = "", user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """语义搜索个人笔记，返回命中的片段和来源文件名。"""
    q = q.strip()
    if not q:
        return {"results": []}
    docs = get_notes_store(user.id).similarity_search(q, k=5)
    return {"results": [
        {
            "content": d.page_content,
            "filename": (d.metadata or {}).get("filename", ""),
            "doc_id": (d.metadata or {}).get("doc_id", ""),
        }
        for d in docs
    ]}

@router.get("")
def list_notes(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [{"doc_id": n.doc_id, "filename": n.filename, "created_at": n.created_at.isoformat() if n.created_at else None} for n in db.query(Note).filter(Note.user_id == user.id).order_by(Note.id.desc()).all()]

@router.delete("/{doc_id}")
def delete_note(doc_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    note = db.query(Note).filter(Note.doc_id == doc_id, Note.user_id == user.id).first()
    if not note: raise HTTPException(404, "note not found")
    # 先清理向量库再删 DB 记录；DB 记录保留便于清理失败时重试
    deleted = delete_note_vectors(user.id, doc_id)
    db.delete(note); db.commit()
    return {"ok": True, "vectors_deleted": deleted}
