"""Run Streamlit with its app-owned config/cache files redirected to D:."""
import os
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
if root.drive.upper() != 'D:':
    raise SystemExit('Launch this project from D:')
sys.path.insert(0, str(root / 'src'))
app_storage = root / '.cache/streamlit'
app_storage.mkdir(parents=True, exist_ok=True)
os.environ['STREAMLIT_BROWSER_GATHER_USAGE_STATS'] = 'false'

from streamlit import file_util
# Streamlit's installed version resolves its global files through this constant.
# An absolute D: path also works with Path.home() / CONFIG_FOLDER_NAME. This is
# process-local: no installed library or user-level configuration is modified.
file_util.CONFIG_FOLDER_NAME = str(app_storage)
if Path(file_util.get_streamlit_file_path('machine_id_v4')).drive.upper() != 'D:':
    raise SystemExit('Streamlit storage redirection failed')

from streamlit.web import cli
sys.argv = ['streamlit', 'run', str(root / 'src/peekaboo/dashboard.py'),
            '--server.address=127.0.0.1', '--server.port=8501', '--server.headless=true',
            '--browser.gatherUsageStats=false', '--theme.base=dark',
            '--theme.primaryColor=#56d5c2', '--theme.backgroundColor=#0b151e',
            '--theme.secondaryBackgroundColor=#122332']
raise SystemExit(cli.main())
