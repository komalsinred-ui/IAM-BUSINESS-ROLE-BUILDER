#request/response models
 
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

class BundleQueryRequest(BaseModel):
    supervisor_level6: Optional[str] = None
    job_code: Optional[str] = None
    assignment_type: Optional[str] = None
    department: Optional[str] = None
    min_group_size: int = 10
    min_role_support: float = 0.60
    min_itemset_support: float = 0.70
    max_k: int = 3

class BundleDiagnoseRequest(BaseModel):
    supervisor_level6: Optional[str] = None
    job_code: Optional[str] = None
    department: Optional[str] = None

    min_group_size: int = 10
    min_role_support: float = 0.60
    min_itemset_support: float = 0.70
    max_k: int = 3

    # how many top items to show in diagnosis
    top_n: int = 10

class NewJoinerRequest(BaseModel):
    job_code: str
    supervisor_level6: Optional[str] = None
    department: Optional[str] = None
    min_role_support: float = 0.70
    top_n: int = 15
    block_high_sod: bool = True

class ExplainAccessRequest(BaseModel):
    user_id: str
    role_name: str

class GenericFilterRequest(BaseModel):
    supervisor_level6: Optional[str] = None
    department: Optional[str] = None
    job_code: Optional[str] = None
    assignment_type: Optional[str] = None

class ExportCSVRequest(BaseModel):
    filename: str
    rows: List[Dict[str, Any]]
