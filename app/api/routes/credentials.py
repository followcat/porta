from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.credential import CredentialCreate, CredentialRead, CredentialUpdate
from app.services.credential_service import CredentialService

router = APIRouter(prefix="/credentials", tags=["credentials"])


@router.get("", response_model=list[CredentialRead])
def list_credentials(db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> list[CredentialRead]:
    return CredentialService(db).list_credentials()


@router.post("", response_model=CredentialRead)
def create_credential(
    payload: CredentialCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CredentialRead:
    credential = CredentialService(db).create_credential(payload, user.id)
    db.commit()
    db.refresh(credential)
    return CredentialRead.model_validate(credential).model_copy(update={"in_use": 0})


@router.get("/{credential_id}", response_model=CredentialRead)
def get_credential(
    credential_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> CredentialRead:
    service = CredentialService(db)
    credential = service.get_credential(credential_id)
    item = CredentialRead.model_validate(credential)
    return item.model_copy(update={"in_use": service.repo.usage_count(credential.id)})


@router.put("/{credential_id}", response_model=CredentialRead)
def update_credential(
    credential_id: int,
    payload: CredentialUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CredentialRead:
    service = CredentialService(db)
    credential = service.update_credential(credential_id, payload, user.id)
    db.commit()
    db.refresh(credential)
    item = CredentialRead.model_validate(credential)
    return item.model_copy(update={"in_use": service.repo.usage_count(credential.id)})


@router.delete("/{credential_id}")
def delete_credential(
    credential_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    CredentialService(db).delete_credential(credential_id, user.id)
    db.commit()
    return {"status": "ok"}
