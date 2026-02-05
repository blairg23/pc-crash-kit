from pc_crash_kit.cli import build_parser


def test_cli_collect_parses():
    parser = build_parser()
    args = parser.parse_args(["collect"])
    assert args.command == "collect"


def test_cli_summarize_parses():
    parser = build_parser()
    args = parser.parse_args(["summarize", "artifacts/test-bundle"])
    assert args.command == "summarize"


def test_cli_doctor_parses():
    parser = build_parser()
    args = parser.parse_args(["doctor"])
    assert args.command == "doctor"
