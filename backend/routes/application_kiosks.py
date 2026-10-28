"""Only Core frontend owns credentials. Public application SDK has no auth API."""
import base64
from fastapi import APIRouter,Depends,Header,HTTPException,Response
from pydantic import BaseModel,ConfigDict,Field,field_validator
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from backend.utils.db_utils import get_db
from backend.services import application_kiosks as service
from backend.services.application_authority_keys import AuthorityReviewKeyError
from backend.services.authority_metadata import AuthorityMetadataError

router=APIRouter(tags=['application-kiosk'])
class Model(BaseModel): model_config=ConfigDict(extra='forbid',strict=True)
class KioskEnrollmentRequest(Model):
    request_id:str=Field(pattern=r'^[0-9a-f]{32}$')
    label:str=Field(min_length=1,max_length=120)
    expires_in_minutes:int=Field(default=15,ge=1,le=1440)
    @field_validator('label')
    @classmethod
    def label_text(cls,value):
        if not value.strip() or any(ord(c)<32 for c in value):raise ValueError('Terminal label required')
        return value.strip()
class KioskEnrollmentClaim(Model):
    request_id:str=Field(pattern=r'^[0-9a-f]{32}$')
    recovery_proof:str=Field(pattern=r'^[A-Za-z0-9_-]{43}$')
    code:str=Field(pattern=r'^[A-Za-z0-9_-]{32}$')
    @field_validator('recovery_proof')
    @classmethod
    def canonical_proof(cls,value):
        data=base64.urlsafe_b64decode(value+'=')
        if len(data)!=32 or base64.urlsafe_b64encode(data).decode().rstrip('=')!=value:raise ValueError('Invalid recovery proof')
        return value
class KioskSessionRequest(Model):
    terminal_id:str=Field(pattern=r'^[0-9a-f]{32}$')
    credential:str=Field(pattern=r'^[A-Za-z0-9_-]{43}$')

def run(db,response,operation):
    response.headers['Cache-Control']='no-store'
    engine=db.get_bind().engine
    if db.new or db.dirty or db.deleted:raise HTTPException(409,'Pairing transaction is unavailable')
    db.rollback()
    try:return operation(engine)
    except HTTPException:raise
    except (ValueError,SQLAlchemyError,AuthorityReviewKeyError,AuthorityMetadataError,service.authority.AuthorityManagementError,OSError):
        raise HTTPException(409,{'code':'kiosk_unavailable'}) from None

@router.post('/{module_id}/kiosk/enrollments',status_code=201)
def enroll(module_id:str,request:KioskEnrollmentRequest,response:Response,authorization:str|None=Header(None),db:Session=Depends(get_db)):
    return run(db,response,lambda engine:service.enroll(engine,module_id,authorization,request))
@router.post('/{module_id}/kiosk/enrollments/claim')
def claim(module_id:str,request:KioskEnrollmentClaim,response:Response,db:Session=Depends(get_db)):
    return run(db,response,lambda engine:service.claim(engine,module_id,request))
@router.post('/{module_id}/kiosk/sessions')
def renew(module_id:str,request:KioskSessionRequest,response:Response,db:Session=Depends(get_db)):
    return run(db,response,lambda engine:service.renew(engine,module_id,request))
@router.get('/{module_id}/kiosk/terminals')
def terminals(module_id:str,response:Response,authorization:str|None=Header(None),db:Session=Depends(get_db)):
    return run(db,response,lambda engine:service.terminals(engine,module_id,authorization))
@router.delete('/{module_id}/kiosk/terminals/{terminal_id}')
def revoke(module_id:str,terminal_id:str,response:Response,authorization:str|None=Header(None),db:Session=Depends(get_db)):
    return run(db,response,lambda engine:service.revoke(engine,module_id,authorization,terminal_id))
