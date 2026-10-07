from fastapi import APIRouter, Depends, File, UploadFile, HTTPException
from pathlib import Path
import uuid
from sqlalchemy.orm import Session
from ..deps import get_current_user
from ..db.models import User
from ..db.session import get_db
from ..llm import llm
from langchain_core.messages import HumanMessage, SystemMessage
from ..vector_store.factory import get_memory_store, get_notes_store

router = APIRouter(prefix="/profile", tags=["impression"])

@router.post("/impression")
async def generate_impression(user: User = Depends(get_current_user)):
    # 从向量库拉用户的记忆和笔记
    mem = get_memory_store(user.id).similarity_search("用户兴趣 习惯 偏好 性格 生活", k=10)
    notes = get_notes_store(user.id).similarity_search("用户兴趣 习惯 偏好", k=5)
    mem_text = "\n".join(d.page_content for d in mem) or "暂无记忆"
    note_text = "\n".join(d.page_content for d in notes) or "暂无笔记"

    prompt = f"""你是用户的生活管家。根据以下你了解到的用户信息，用第二人称写一段"AI 对你的印象"，150字左右：
- 概括他的兴趣爱好
- 他的生活习惯/作息
- 他的消费倾向
- 一句话性格画像
要求：语气亲切、像朋友，不要列点，自然段。如果信息不足，就基于现有信息推断，不要说"我不了解"。

记忆：
{mem_text}

笔记：
{note_text}"""
    resp = llm.invoke([
        SystemMessage(content="你擅长通过生活细节洞察一个人。"),
        HumanMessage(content=prompt)
    ])
    return {"impression": resp.content}


@router.post("/avatar")
async def upload_avatar(file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """上传头像，最大 5MB，支持 jpg/png/webp/gif。"""
    if not file.filename or file.filename.lower().split(".")[-1] not in {"jpg", "jpeg", "png", "webp", "gif"}:
        raise HTTPException(400, "仅支持 jpg/png/webp/gif 图片")
    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(400, "图片不能超过 5MB")
    ext = file.filename.lower().split(".")[-1]
    av_dir = Path("uploads/avatars")
    av_dir.mkdir(parents=True, exist_ok=True)
    name = f"u{user.id}_{uuid.uuid4().hex[:8]}.{ext}"
    (av_dir / name).write_bytes(data)
    user.avatar = f"notes/uploads/avatars/{name}"
    db.commit()
    return {"avatar": user.avatar}
