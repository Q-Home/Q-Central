from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from .db import get_session
from .models import Device
from .schemas import RegisterSerialRequest, RegisterSerialResponse
from .security import hash_secret, new_token, require_admin

router = APIRouter(prefix='/api/devices', tags=['Devices'])


@router.post('/add', response_model=RegisterSerialResponse)
def add_device(body: RegisterSerialRequest, session: Session = Depends(get_session), actor: str = Depends(require_admin)):
    if session.get(Device, body.serial):
        raise HTTPException(status_code=409, detail='serial already exists')
    claim_token = new_token('claim')
    device = Device(serial=body.serial, claim_token_hash=hash_secret(claim_token), name=body.name, customer=body.customer, site=body.site, model=body.model)
    session.add(device)
    session.commit()
    return RegisterSerialResponse(serial=body.serial, claim_token=claim_token)
