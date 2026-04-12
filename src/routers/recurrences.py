"""重复任务 API"""
from fastapi import APIRouter, HTTPException

from src.models import Recurrence, RecurrenceCreate
from src.config import RECURRENCES_FILE
from src.storage import JsonStore
from src.utils.id_gen import generate_recurrence_id

router = APIRouter(prefix="/recurrences", tags=["recurrences"])
recurrence_store = JsonStore(RECURRENCES_FILE, Recurrence)


@router.post("", response_model=Recurrence, status_code=201)
async def create_recurrence(data: RecurrenceCreate):
    rec = Recurrence(id=generate_recurrence_id(), **data.model_dump())
    recurrence_store.add(rec)
    return rec


@router.get("", response_model=list[Recurrence])
async def list_recurrences():
    return recurrence_store.load_all()


@router.put("/{rec_id}", response_model=Recurrence)
async def update_recurrence(rec_id: str, data: RecurrenceCreate):
    rec = recurrence_store.find_by_id(rec_id)
    if not rec:
        raise HTTPException(404, "Recurrence not found")
    updated = Recurrence(
        id=rec_id, **data.model_dump(),
        last_generated=rec.last_generated,
    )
    recurrence_store.update(rec_id, updated)
    return updated


@router.delete("/{rec_id}")
async def delete_recurrence(rec_id: str):
    if not recurrence_store.delete(rec_id):
        raise HTTPException(404, "Recurrence not found")
    return {"detail": "Deleted"}
