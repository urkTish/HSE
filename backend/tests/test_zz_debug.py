import pytest
from sqlalchemy import select
from app.models import Wap, WapCrew, Worker, Zone
pytestmark = pytest.mark.usefixtures("access_seed", "noon")

def test_dbg(api, db):
    zones = {z.id: z.code for z in db.scalars(select(Zone))}
    for w in db.scalars(select(Wap).where(Wap.status.in_(["active","approved","suspended"]))):
        print("DBG", w.wap_no, w.status, [zones.get(z) for z in w.zone_ids], w.windows)
        for c in db.scalars(select(WapCrew).where(WapCrew.wap_id == w.id)):
            wk = db.get(Worker, c.worker_id)
            print("DBG   ", wk.full_name_en, c.crew_role, c.status, c.exclusion_reasons, c.escorted, c.removed_at)
