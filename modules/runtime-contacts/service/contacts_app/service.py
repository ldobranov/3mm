from three_mm_crud import CrudService
from .definition import DEFINITION

def create_service(application):
    return CrudService(application,DEFINITION)
