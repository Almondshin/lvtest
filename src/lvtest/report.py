from __future__ import annotations

import json
import os
from pathlib import Path

from lvtest.errors import LvtestError
from lvtest.models import Session, Thread, Turn
from lvtest.paths import reports_dir
from lvtest.rubric import Rubric
from lvtest.scoring import CONFIDENCE_THRESHOLD, AxisStats, Overall, level_from_overall

END_REASON_LABEL = {"done": "확신도 충족", "max": "문항 상한 도달", "user_stop": "사용자 중단"}
KIND_LABEL = {"dont_know": "(모르겠다)", "pass": "(넘어감)", "ungradable": "(채점 불가)"}


def report_filename(session: Session) -> str:
    return f"{session.created_at[:10]}-{session.id}.md"


def report_path_for(session: Session) -> Path:
    return reports_dir() / report_filename(session)


# ---------- history index ----------

def index_path() -> Path:
    return reports_dir() / "index.json"


def load_index() -> list[dict]:
    p = index_path()
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise LvtestError("index_corrupt", f"{p} is not valid JSON: {e}", path=str(p)) from e
    return data if isinstance(data, list) else []


def upsert_index(index: list[dict], entry: dict) -> None:
    index[:] = [e for e in index if e.get("id") != entry["id"]] + [entry]
    index.sort(key=lambda e: e.get("created_at", ""))
    path = index_path()
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def previous_entry(index: list[dict], session: Session) -> dict | None:
    candidates = [
        e for e in index
        if e.get("track") == session.track and e.get("id") != session.id and e.get("created_at", "") < session.created_at
    ]
    return max(candidates, key=lambda e: e["created_at"]) if candidates else None


def index_entry(session: Session, stats: dict[str, AxisStats], overall: Overall, path) -> dict:
    return {
        "id": session.id,
        "date": session.created_at[:10],
        "created_at": session.created_at,
        "finished_at": session.finished,
        "track": session.track,
        "rubric_version": session.rubric_version,
        "end_reason": session.end_reason,
        "overall": overall.score,
        "level": overall.level,
        "axes": {k: (None if s.score is None else round(s.score, 2)) for k, s in stats.items()},
        "report_path": str(path),
    }


def build_comparison(prev: dict, stats: dict[str, AxisStats], overall: Overall, session: Session) -> dict:
    out = {"previous_id": prev["id"], "previous_date": prev.get("date"), "comparable": prev.get("rubric_version") == session.rubric_version}
    if not out["comparable"]:
        out["reason"] = f"루브릭 버전이 다름 (이전 v{prev.get('rubric_version')}, 현재 v{session.rubric_version})"
        return out

    def delta(a, b):
        return None if a is None or b is None else round(b - a, 2)

    out["axes"] = {}
    for k, s in stats.items():
        p = prev.get("axes", {}).get(k)
        n = None if s.score is None else round(s.score, 2)
        out["axes"][k] = {"prev": p, "now": n, "delta": delta(p, n)}
    out["overall"] = {"prev": prev.get("overall"), "now": overall.score, "delta": delta(prev.get("overall"), overall.score)}
    return out


# ---------- rendering ----------

def _cell(text: str, limit: int = 140) -> str:
    t = " ".join(text.split()).replace("|", "\\|")
    return t if len(t) <= limit else t[: limit - 1] + "…"


def _fmt_score(x: float | None) -> str:
    return "—" if x is None else f"{x:.1f}"


def _fmt_delta(x: float | None) -> str:
    return "—" if x is None else f"{x:+.1f}"


def _best_turn(session: Session, axis: str) -> Turn | None:
    turns = [t for t in session.turns_for_axis(axis) if t.grade and t.grade.answer_kind == "answered"]
    return max(turns, key=lambda t: t.grade.strength) if turns else None


def _gaps(session: Session, axis: str) -> list[str]:
    seen: list[str] = []
    for t in session.turns_for_axis(axis):
        if t.grade:
            for g in t.grade.gaps:
                if g not in seen:
                    seen.append(g)
    return seen


def _turn_line(turn: Turn) -> list[str]:
    lines = [f"**Q{turn.question_no} (S{turn.stage})** {turn.question}"]
    g = turn.grade
    if g is None:
        lines.append("> (미응답)")
    elif g.answer_kind != "answered":
        lines.append(f"> {KIND_LABEL[g.answer_kind]} · 근거 L{g.level_evidence} · strength {g.strength:.1f}")
    else:
        lines.append(f"> 답변 인용: {_cell(g.quote, 400)}")
        lines.append(f"> 근거 L{g.level_evidence} · strength {g.strength:.1f}")
    lines.append("")
    return lines


def render_report(
    session: Session, rubric: Rubric, stats: dict[str, AxisStats], overall: Overall, comparison: dict | None
) -> str:
    name = {a.key: a.name for a in rubric.axes}
    L: list[str] = []
    L.append(f"# {rubric.label} 레벨테스트 결과 — {session.created_at[:10]}")
    L.append("")

    # 종합
    if overall.level is None:
        L.append("## 종합: 판정 불가 (채점된 답변 없음)")
    else:
        head = f"## 종합: L{overall.level} {rubric.levels[overall.level]}"
        if overall.neighbor is not None:
            head += f" (L{overall.neighbor} 경계)"
        L.append(head)
        L.append("")
        bottleneck = f" · 병목: {name[overall.bottleneck]} {_fmt_score(stats[overall.bottleneck].score)}" if overall.bottleneck else ""
        L.append(f"평균 {overall.score:.1f}{bottleneck}")
    L.append("")
    reason = END_REASON_LABEL.get(session.end_reason or "", session.end_reason or "—")
    L.append(f"종료 사유: {reason} ({session.question_no}문항) · 루브릭 v{session.rubric_version}")
    if overall.undetermined:
        L.append("")
        L.append("> 미확정 축 (채점된 답변 없음): " + ", ".join(name[k] for k in overall.undetermined))
    low = [k for k, s in stats.items() if s.score is not None and s.confidence < CONFIDENCE_THRESHOLD]
    if low:
        L.append("")
        L.append(f"> 확신 부족 축 ({CONFIDENCE_THRESHOLD} 미만): " + ", ".join(name[k] for k in low))
    L.append("")

    # 축별 결과
    L.append("## 축별 결과")
    L.append("")
    L.append("| 축 | 점수 | 확신 | 근거 (답변 인용) | 부족했던 것 |")
    L.append("|---|---|---|---|---|")
    for k, s in stats.items():
        best = _best_turn(session, k)
        quote = _cell(best.grade.quote) if best else "—"
        gaps = _cell(", ".join(_gaps(session, k))) or "—"
        L.append(f"| {name[k]} | {_fmt_score(s.score)} | {s.confidence:.2f} | {quote} | {gaps} |")
    L.append("")

    # 강점 / 약점
    scored = sorted(((k, round(s.score, 2)) for k, s in stats.items() if s.score is not None), key=lambda kv: -kv[1])
    L.append("## 강점")
    L.append("")
    for k, sc in scored[:2]:
        best = _best_turn(session, k)
        sig = f" — {', '.join(best.grade.signals[:2])}" if best and best.grade.signals else ""
        L.append(f"- {name[k]} ({sc:.1f}){sig}")
    if not scored:
        L.append("- (없음)")
    L.append("")
    L.append("## 약점")
    L.append("")
    axis_order = {a.key: i for i, a in enumerate(rubric.axes)}
    weakest = sorted(scored, key=lambda kv: (kv[1], axis_order[kv[0]]))[:2]
    for k, sc in weakest:
        gaps = _gaps(session, k)
        gap = f" — {', '.join(gaps[:2])}" if gaps else ""
        L.append(f"- {name[k]} ({sc:.1f}){gap}")
    if not scored:
        L.append("- (없음)")
    L.append("")

    # 다음 레벨
    L.append("## 다음 레벨로 가려면")
    L.append("")
    for k, sc in weakest:
        cur, _ = level_from_overall(sc)
        nxt = min(5, cur + 1)
        if nxt == cur:
            continue
        L.append(f"### {name[k]}: L{cur} → L{nxt}")
        L.append("")
        for anchor in rubric.axis(k).levels[nxt]:
            L.append(f"- {anchor}")
        L.append("")
    if not weakest:
        L.append("- (없음)")
        L.append("")

    # 비교
    if comparison is not None:
        L.append("## 지난 결과와 비교")
        L.append("")
        L.append(f"이전 세션: {comparison['previous_id']} ({comparison.get('previous_date')})")
        L.append("")
        if not comparison["comparable"]:
            L.append(f"루브릭 변경으로 비교 불가 — {comparison['reason']}")
        else:
            L.append("| 축 | 이전 | 이번 | 변화 |")
            L.append("|---|---|---|---|")
            for k, d in comparison["axes"].items():
                L.append(f"| {name[k]} | {_fmt_score(d['prev'])} | {_fmt_score(d['now'])} | {_fmt_delta(d['delta'])} |")
            o = comparison["overall"]
            L.append(f"| **종합** | {_fmt_score(o['prev'])} | {_fmt_score(o['now'])} | {_fmt_delta(o['delta'])} |")
        L.append("")

    # 총평
    if session.summary:
        L.append("## 총평")
        L.append("")
        L.append(session.summary.strip())
        L.append("")

    # 부록
    L.append("## 부록: 전체 문답")
    L.append("")
    for t in session.threads:
        hook = f" — 훅: {t.hook}" if t.hook else ""
        L.append(f"### {name[t.axis]}{hook}")
        L.append("")
        for turn in t.turns:
            L.extend(_turn_line(turn))
    return "\n".join(L).rstrip() + "\n"
