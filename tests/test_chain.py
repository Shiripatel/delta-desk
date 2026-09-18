from datetime import date

from deltadesk.analytics.chain import max_pain, pcr, walls
from deltadesk.schemas import ChainRow


def _row(k, ce_oi, pe_oi):
    return ChainRow(strike=k, expiry=date(2026, 9, 22), ce_ltp=1, pe_ltp=1, ce_oi=ce_oi, pe_oi=pe_oi)


def test_max_pain_and_walls():
    chain = [_row(25200, 1000, 9000), _row(25300, 2000, 5000), _row(25400, 3000, 3000),
             _row(25500, 8000, 2000), _row(25600, 4000, 1000)]
    assert max_pain(chain) == 25400
    cw, pw = walls(chain, 25400)
    assert cw == 25500 and pw == 25200
    assert abs(pcr(chain) - 20000 / 18000) < 1e-9
