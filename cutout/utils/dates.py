from datetime import datetime


def isodatetime_from_db(value: datetime):
    if value == None:
        return None
    return value.isoformat()
