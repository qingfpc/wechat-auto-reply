from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
WEB_DIR = Path(__file__).resolve().parent / "web"
DB_PATH = DATA_DIR / "brain.sqlite3"
LAST_SHOT = DATA_DIR / "last_screen.png"
DEFAULT_CONFIG = CONFIG_DIR / "default.yaml"
