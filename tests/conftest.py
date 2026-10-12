from pathlib import Path
import shutil
import pytest

@pytest.fixture
def tmp_path(request):
    root = Path.cwd() / ".test-tmp" / request.node.name
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True)
    yield root
    shutil.rmtree(root, ignore_errors=True)
