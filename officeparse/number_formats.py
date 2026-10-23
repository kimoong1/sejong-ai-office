"""Conservative semantic number/date rendering; raw values are always retained."""
import datetime as dt
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re

BUILTINS = {0:'General',1:'0',2:'0.00',3:'#,##0',4:'#,##0.00',9:'0%',10:'0.00%',
            14:'mm-dd-yy',15:'d-mmm-yy',16:'d-mmm',17:'mmm-yy',18:'h:mm AM/PM',19:'h:mm:ss AM/PM',
            20:'h:mm',21:'h:mm:ss',22:'m/d/yy h:mm',45:'mm:ss',46:'[h]:mm:ss',47:'mmss.0',49:'@'}


def semantic_value(raw, code, date1904=False):
    if raw is None or not code or code in ('General','@'):
        return raw
    try:
        number=Decimal(raw)
        if not number.is_finite():
            return raw
    except (InvalidOperation, ValueError):
        return raw
    cleaned=re.sub(r'"[^"]*"|\\.|_.|\*.', '', code.split(';')[0]).lower()
    elapsed=re.search(r'\[([hms]+)\]',cleaned)
    has_date=bool(re.search(r'[yd]', cleaned))
    has_time=bool(re.search(r'[hs]',re.sub(r'\[[^]]*\]','',cleaned)))
    try:
        if elapsed:
            total=int((number*86400).to_integral_value(rounding=ROUND_HALF_UP))
            unit=elapsed[1][0]
            if unit=='s':return str(total)
            if unit=='m':return f'{total//60}:{total%60:02}' if 's' in cleaned else str(total//60)
            return f'{total//3600}:{total//60%60:02}:{total%60:02}' if 's' in cleaned else f'{total//3600}:{total//60%60:02}'
        if has_date or has_time:
            if number<0:return raw
            days=int(number)
            seconds=int(((number-days)*86400).to_integral_value(rounding=ROUND_HALF_UP))
            if seconds==86400:days+=1;seconds=0
            time=f'{seconds//3600:02}:{seconds//60%60:02}'+(f':{seconds%60:02}' if 's' in cleaned else '')
            if not has_date:return time
            if not date1904 and days==60:date='1900-02-29'
            else:
                epoch=dt.date(1904,1,1) if date1904 else dt.date(1899,12,30)
                date=(epoch+dt.timedelta(days=days+(1 if not date1904 and 0<days<60 else 0))).isoformat()
            return date+' '+time if has_time else date
        if re.fullmatch(r'0{2,}',cleaned) and number==number.to_integral_value():
            return ('-' if number<0 else '')+str(abs(int(number))).zfill(len(cleaned))
        match=re.fullmatch(r'0(?:\.(0+))?%',cleaned)
        if match:return f'{number*100:.{len(match[1] or "")}f}%'
    except (ValueError,OverflowError,InvalidOperation):
        pass
    return raw
