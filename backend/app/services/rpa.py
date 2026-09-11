import asyncio, uuid
from ..config import settings
async def run_rpa(invoice_id):
    if settings.rpa_mode!='mock':
        return {'status':'NOT_CONFIGURED','message':'Real SAP/RPA adapter is not configured','steps':[]}
    steps=['Bot session started on VM','Logged in to SAP, opened MIRO','Vendor identified, header data entered','GRN line items fetched & matched','TDS codes applied','Simulate posting — balance check','Document posted (MM + FI)']
    await asyncio.sleep(0.5)
    return {'status':'COMPLETED','session_id':f'RPA-{uuid.uuid4().hex[:12].upper()}','sap_document':f'50{invoice_id:08d}','steps':steps}
