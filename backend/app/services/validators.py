def validate_extraction(data):
    errors=[]
    for field in ('vendor','invoice_number','invoice_date'):
        if not getattr(data,field,None): errors.append(f'{field.replace("_"," ").title()} is required')
    if getattr(data,'total',0) <= 0: errors.append('Invoice total must be greater than zero')
    lines=getattr(data,'lines',[]) or []
    if not lines: errors.append('At least one line item is required')
    calculated=sum(float(getattr(x,'amount',0) or 0) for x in lines)
    total=float(getattr(data,'total',0) or 0)
    tax=float(getattr(data,'tax',0) or 0)
    if abs((calculated+tax)-total)>0.01: errors.append(f'Line total mismatch: lines + tax = {calculated+tax:.2f}, invoice total = {total:.2f}')
    if float(getattr(data,'confidence',0) or 0) < 0.75: errors.append('Extraction confidence is below 75%')
    return errors
