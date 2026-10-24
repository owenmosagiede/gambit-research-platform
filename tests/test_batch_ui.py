"""Batch retirement leaves no served asset, browser request, timer or control."""
from pathlib import Path
import shutil
import subprocess
import unittest
from api.application import ASSETS

ROOT = Path(__file__).resolve().parents[1]


class BatchUITests(unittest.TestCase):
    def test_batch_surface_is_absent_from_shipped_workspace_and_assets(self):
        html = (ROOT / 'ui/index.html').read_text()
        self.assertNotIn('/batches.js', html)
        self.assertNotIn('/batches.js', ASSETS)
        self.assertNotIn('Research batches', html)
        for name in ('batch-title', 'batch-select', 'batch-status', 'batch-detail', 'batch-refresh'):
            self.assertNotIn('id="' + name + '"', html)

    def test_retained_compatibility_file_does_no_browser_work(self):
        node = shutil.which('node')
        if not node: self.skipTest('Node.js required for the inert compatibility check')
        script = r'''
const fs=require('fs'),vm=require('vm');
const forbidden=()=>{throw new Error('Retired batch script performed browser work');};
const unavailable=new Proxy({}, {get:forbidden,set:forbidden});
vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'), {
  document:unavailable,window:unavailable,fetch:forbidden,
  setTimeout:forbidden,setInterval:forbidden,addEventListener:forbidden
});
'''
        result = subprocess.run([node, '-e', script, str(ROOT / 'ui/batches.js')],
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
