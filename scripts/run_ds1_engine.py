"""Run the packaged research engine with the shared DS1 list, Telegram disabled."""
import importlib.util
import os
import sys
from pathlib import Path
from scripts.ds1_universe import symbols, watchlist_version


def load_engine(path=None):
    path = path or Path(__file__).resolve().parents[1] / "engine" / "main.py"
    spec = importlib.util.spec_from_file_location("ds1_packaged_engine", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.DS1 = symbols()
    return module


def main():
    # The user's Telegram opt-out also applies to direct invocations of this runner.
    os.environ["TELEGRAM_BOT_TOKEN"] = ""
    os.environ["TELEGRAM_CHAT_ID"] = ""
    engine = load_engine()
    print(f"DS1 membership={watchlist_version()} count={len(engine.DS1)}; research only")
    return engine.main()


if __name__ == "__main__":
    raise SystemExit(main())
