from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless((ROOT / 'reports/latest.json').exists(), 'Run the local experiment first')
class DashboardSmoke(unittest.TestCase):
    def test_results_and_both_replay_modes(self):
        from streamlit import file_util
        file_util.CONFIG_FOLDER_NAME = str(ROOT / '.cache/streamlit')
        self.assertEqual(Path(file_util.get_streamlit_file_path('machine_id_v4')).drive.upper(), 'D:')
        from streamlit.testing.v1 import AppTest
        app = AppTest.from_file(str(ROOT / 'src/peekaboo/dashboard.py'), default_timeout=60).run()
        self.assertFalse(list(app.exception), list(app.exception))
        self.assertEqual(app.metric[0].label, 'Test accuracy')
        app.button[0].click().run()
        self.assertFalse(list(app.exception), list(app.exception))
        self.assertTrue(any('Original classifier:' in item.value for item in app.markdown))
        app.select_slider[0].set_value(20)
        app.button[0].click().run()
        self.assertFalse(list(app.exception), list(app.exception))
        self.assertTrue(any('Retrained classifier:' in item.value for item in app.markdown))


if __name__ == '__main__':
    unittest.main()
