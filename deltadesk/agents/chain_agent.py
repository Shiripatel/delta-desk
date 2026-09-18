"""chain.agent: IV rank, skew, PCR, max pain, walls, expected move."""
from __future__ import annotations

import math

from deltadesk.analytics.chain import atm_row, iv_at_delta, max_pain, pcr, walls
from deltadesk.schemas import ChainStats, Snapshot


class ChainAgent:
    name = "chain"
    version = "0.1"

    def __init__(self, iv_history: list[float] | None = None) -> None:
        # Daily ATM IV history (one value per session). Phase 1 loads this from recorded days.
        self.iv_history = iv_history or []

    def step(self, snap: Snapshot, realised_vol: float) -> ChainStats:
        row = atm_row(snap.chain, snap.atm)
        ivs = [v for v in (row.ce_iv, row.pe_iv) if v]
        atm_iv = sum(ivs) / len(ivs) if ivs else 0.0
        rank = None
        if len(self.iv_history) >= 20:
            lo, hi = min(self.iv_history), max(self.iv_history)
            rank = 100 * (atm_iv - lo) / (hi - lo) if hi > lo else 50.0
        em = snap.fut * atm_iv * math.sqrt(snap.t_years)
        cw, pw = walls(snap.chain, snap.atm)
        p25 = iv_at_delta(snap.chain, 0.25, call=False)
        c25 = iv_at_delta(snap.chain, 0.25, call=True)
        skew = ((p25 or atm_iv) - (c25 or atm_iv)) * 100
        return ChainStats(atm_iv=atm_iv, iv_rank=rank, pcr_oi=pcr(snap.chain), max_pain=max_pain(snap.chain),
                          call_wall=cw, put_wall=pw, expected_move_pts=em,
                          expected_move_pct=em / snap.spot * 100, skew=skew,
                          iv_minus_rv=(atm_iv - realised_vol) * 100)
