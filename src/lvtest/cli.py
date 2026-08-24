import json
import sys

import typer

from lvtest import __version__, engine
from lvtest.errors import LvtestError

app = typer.Typer(add_completion=False, help="이력서 기반 백엔드 레벨테스트 엔진")


def _emit(obj) -> None:
    typer.echo(json.dumps(obj, ensure_ascii=False, indent=2))


def _run(fn, *args, **kwargs) -> None:
    try:
        _emit(fn(*args, **kwargs))
    except LvtestError as e:
        _emit(e.to_dict())
        raise typer.Exit(code=1)
    except Exception as e:  # noqa: BLE001 — CLI boundary: stdout must stay a single JSON object
        _emit({"error": {"code": "internal", "message": f"{type(e).__name__}: {e}"}})
        raise typer.Exit(code=1)


def _read_json_arg(value: str, what: str) -> dict:
    raw = sys.stdin.read() if value == "-" else value
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise LvtestError("invalid_json", f"{what}: {e.msg} at pos {e.pos}")
    if not isinstance(data, dict):
        raise LvtestError("invalid_json", f"{what}: top-level must be a JSON object")
    return data


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", help="버전 출력"),
) -> None:
    if version:
        _emit({"lvtest": __version__})
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()


@app.command(help="이력서로 새 세션을 만든다")
def start(
    resume_path: str = typer.Argument(..., help="pdf / docx / md 이력서 경로"),
    track: str = typer.Option("backend", "--track"),
) -> None:
    _run(engine.start, resume_path, track)


@app.command(help="Claude가 만든 축별 프로파일 JSON을 저장한다 (--json - 이면 stdin)")
def profile(session_id: str, json_: str | None = typer.Option(None, "--json")) -> None:
    if json_ is None:
        _emit(LvtestError("invalid_json", "pass --json <profile> (or --json - for stdin)").to_dict())
        raise typer.Exit(code=1)
    _run(lambda: engine.profile(session_id, _read_json_arg(json_, "profile")))


@app.command("next", help="다음에 물을 축·단계·앵커를 돌려준다 (상태 변경 없음)")
def next_cmd(session_id: str) -> None:
    _run(engine.next_question, session_id)


@app.command(help="실제로 던진 질문을 기록한다")
def ask(session_id: str, question: str | None = typer.Option(None, "--question")) -> None:
    if question is None:
        _emit(LvtestError("invalid_question", 'pass --question "<text>"').to_dict())
        raise typer.Exit(code=1)
    if question == "-":
        question = sys.stdin.read()
    _run(engine.ask, session_id, question)


@app.command(help="채점 JSON을 검증·기록한다 (--json - 이면 stdin, --ungradable 이면 채점 불가로 기록)")
def grade(
    session_id: str,
    json_: str | None = typer.Option(None, "--json"),
    ungradable: bool = typer.Option(False, "--ungradable"),
) -> None:
    if ungradable:
        _run(engine.grade_ungradable, session_id)
        return
    if json_ is None:
        _emit(LvtestError("invalid_json", "pass --json <grade> (or --json - for stdin) or --ungradable").to_dict())
        raise typer.Exit(code=1)
    _run(lambda: engine.grade(session_id, _read_json_arg(json_, "grade")))


@app.command(help="현재 상태와 다음 할 일을 돌려준다 (복구용)")
def status(session_id: str) -> None:
    _run(engine.status, session_id)


@app.command(help="리포트를 만든다. --summary 로 총평을 붙여 다시 호출 가능")
def finish(
    session_id: str,
    reason: str | None = typer.Option(None, "--reason", help="done | max | user_stop"),
    summary: str | None = typer.Option(None, "--summary"),
) -> None:
    _run(engine.finish, session_id, reason, summary)


@app.command(help="완료된 세션 목록 (최신순)")
def history() -> None:
    _run(engine.history)


@app.command(help="미완료 세션 목록")
def sessions() -> None:
    _run(engine.sessions)


if __name__ == "__main__":
    app()
