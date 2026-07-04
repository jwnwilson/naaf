from urllib.parse import quote
from uuid import UUID

from adapters.database.uow import SqlUnitOfWork
from adapters.storage.keys import attachment_key
from crud_router import Envelope, ok
from domain.attachments.attachment import Attachment
from domain.attachments.validation import is_allowed_content_type, validate_filename
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from starlette.responses import StreamingResponse
from storage import Storage, StorageNotFound

from interactors.api.contract import AttachmentOut, iso
from interactors.api.deps import get_max_attachment_bytes, get_storage, get_uow

router = APIRouter(prefix="/work-items/{work_item_id}/attachments", tags=["attachments"])


def _out(att: Attachment, work_item_id: str) -> AttachmentOut:
    return AttachmentOut(
        id=att.id,
        filename=att.filename,
        contentType=att.content_type,
        size=att.size,
        url=f"/work-items/{work_item_id}/attachments/{att.id}",
        createdAt=iso(att.created_at),
    )


def _require_item(uow: SqlUnitOfWork, work_item_id: str) -> None:
    uow.work_items.read(work_item_id)  # RecordNotFound -> 404 via exception handler


def _find_by_name(uow: SqlUnitOfWork, work_item_id: str, filename: str) -> Attachment | None:
    page = uow.attachments.read_multi(
        filters={"work_item_id": work_item_id, "filename": filename}
    )
    return page.results[0] if page.results else None


@router.post("", response_model=Envelope[AttachmentOut])
async def upload_attachment(
    work_item_id: UUID,
    file: UploadFile = File(...),  # noqa: B008
    overwrite: bool = Form(False),  # noqa: B008
    uow: SqlUnitOfWork = Depends(get_uow),  # noqa: B008
    storage: Storage = Depends(get_storage),  # noqa: B008
    max_bytes: int = Depends(get_max_attachment_bytes),  # noqa: B008
):
    wid = work_item_id.hex
    _require_item(uow, wid)

    filename = validate_filename(file.filename or "")
    content_type = (file.content_type or "application/octet-stream").split(";")[0].strip()
    if not is_allowed_content_type(content_type):
        raise HTTPException(status_code=415, detail=f"unsupported file type: {content_type}")

    data = await file.read()
    if len(data) > max_bytes:
        raise HTTPException(status_code=413, detail="file too large")

    existing = _find_by_name(uow, wid, filename)
    if existing and not overwrite:
        raise HTTPException(status_code=409, detail=f"{filename} already exists")

    storage.put_bytes(attachment_key(wid, filename), data, content_type)
    if existing:
        att = uow.attachments.update(
            existing.id,
            existing.model_copy(update={"content_type": content_type, "size": len(data)}),
        )
    else:
        att = uow.attachments.create(
            Attachment(
                owner_id="",
                work_item_id=wid,
                filename=filename,
                content_type=content_type,
                size=len(data),
            )
        )
    return ok(_out(att, wid))


@router.get("", response_model=Envelope[list[AttachmentOut]])
def list_attachments(
    work_item_id: UUID,
    uow: SqlUnitOfWork = Depends(get_uow),  # noqa: B008
):
    wid = work_item_id.hex
    _require_item(uow, wid)
    page = uow.attachments.read_multi(filters={"work_item_id": wid}, order_by="created_at")
    return ok([_out(a, wid) for a in page.results])


@router.get("/{attachment_id}")
def download_attachment(
    work_item_id: UUID,
    attachment_id: UUID,
    uow: SqlUnitOfWork = Depends(get_uow),  # noqa: B008
    storage: Storage = Depends(get_storage),  # noqa: B008
):
    wid = work_item_id.hex
    _require_item(uow, wid)
    att = uow.attachments.read(attachment_id.hex)
    if att.work_item_id != wid:
        raise HTTPException(status_code=404, detail="attachment not found")
    try:
        data = storage.get_bytes(attachment_key(wid, att.filename))
    except StorageNotFound as err:
        raise HTTPException(status_code=404, detail="file bytes missing") from err
    filename_star = quote(att.filename)
    return StreamingResponse(
        iter([data]),
        media_type=att.content_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename_star}"},
    )


@router.delete("/{attachment_id}", response_model=Envelope[dict])
def delete_attachment(
    work_item_id: UUID,
    attachment_id: UUID,
    uow: SqlUnitOfWork = Depends(get_uow),  # noqa: B008
    storage: Storage = Depends(get_storage),  # noqa: B008
):
    wid = work_item_id.hex
    _require_item(uow, wid)
    att = uow.attachments.read(attachment_id.hex)
    if att.work_item_id != wid:
        raise HTTPException(status_code=404, detail="attachment not found")
    uow.attachments.delete(att.id)
    storage.delete(attachment_key(wid, att.filename))
    return ok({"deleted": att.id})
