from sqlalchemy.orm import Session
import pytest
from app.services.followup import requirements as rq
from tests.fu_helpers import fu2, reqs

pytestmark = pytest.mark.usefixtures("fu_seed", "clock")


def test_smoke(db: Session) -> None:
    i = fu2(db)
    rs = reqs(db, i)
    from app.core.clock import now
    subs = rq._valid_subs(db, [r.id for r in rs.values()])
    print(i.ref, {k: (r.due_at.isoformat(), rq.status_of(r, subs.get(r.id, []), now()).value) for k, r in rs.items()})
