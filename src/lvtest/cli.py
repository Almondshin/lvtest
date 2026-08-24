import json
import sys

import typer

from lvtest import __version__
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
