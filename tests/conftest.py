import sys
import tempfile
from pathlib import Path

SERVER_DIR = Path(__file__).parent.parent / "server"
sys.path.insert(0, str(SERVER_DIR))

from main import app  # noqa: E402
from services.workspace import ProjectWorkspace  # noqa: E402


def open_temp_workspace(init_db: bool = False) -> ProjectWorkspace:
    """Create a fresh, empty project workspace in a temp dir and open it on `app.state`.

    Used by test setup_function()s in place of the old in-memory clear_dataset() --
    each test now gets a brand-new on-disk workspace instead of a shared global dict.
    `init_db` is off by default since it spawns a `prisma migrate deploy` subprocess
    (a few seconds); pass True only for tests that touch the component library.
    """
    root = Path(tempfile.mkdtemp()) / "workspace"
    workspace = ProjectWorkspace.create(root, "Test Project", init_db=init_db)
    app.state.workspace = workspace
    return workspace
