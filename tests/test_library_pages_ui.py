"""Shipped workspace navigation and retired page controls."""
from html.parser import HTMLParser
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PageStructureTests(unittest.TestCase):
    def test_sidebar_only_remaining_navigation_and_queue_is_live(self):
        html = (ROOT / 'ui/index.html').read_text()
        aside = html.split('<aside', 1)[1].split('</aside>', 1)[0]
        for page in ('experiment', 'signals', 'ledger'):
            self.assertIn('data-page="' + page + '"', aside)
        self.assertEqual(aside.count('data-page='), 3)
        self.assertNotIn('<section', aside)
        self.assertNotIn('library-items', aside)
        experiment = html.split('<main id="experiment-inputs"', 1)[1].split('</main>', 1)[0]
        for label in ('Trial queue', 'Sequential execution', 'queue-board', 'queue-status'):
            self.assertIn(label, experiment)
        self.assertIn('/queue.js', html)

    def test_pit_page_and_signal_filters_are_not_shipped(self):
        html = (ROOT / 'ui/index.html').read_text()
        for retired in ('pit-page', 'pit-search', 'pit-provider', 'pit-frequency', 'pit-from', 'pit-to',
                        'pit-clear', 'library-items', 'dataset-details', 'signal-search',
                        'signal-provider', 'signal-state', 'signal-from', 'signal-to', 'signal-clear'):
            self.assertNotIn(f'id="{retired}"', html)
        self.assertNotIn('data-page="pit"', html)
        self.assertNotIn('PIT Data Library', html)
        self.assertNotIn('Signal search and filters', html)
        self.assertIn('id="ledger-search"', html)
        self.assertIn('id="ledger-state"', html)
        self.assertIn('id="signal-detail"', html)

    def test_shipped_scripts_do_not_poll_retired_pages(self):
        class Scripts(HTMLParser):
            def __init__(self):
                super().__init__()
                self.sources = []
            def handle_starttag(self, tag, attrs):
                if tag == 'script':
                    self.sources.append(dict(attrs)['src'])
        parser = Scripts()
        parser.feed((ROOT / 'ui/index.html').read_text())
        self.assertNotIn('/library.js', parser.sources)
        self.assertNotIn('/batches.js', parser.sources)
        for source in parser.sources:
            with self.subTest(source=source):
                code = (ROOT / 'ui' / source.lstrip('/')).read_text()
                self.assertNotIn('/api/pit-library', code)
                self.assertNotIn('/api/batches', code)

    def test_unique_ids_and_all_controls_are_labelled(self):
        class Parser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.ids = []
                self.controls = []
                self.labels = []
            def handle_starttag(self, tag, attrs):
                attributes = dict(attrs)
                if 'id' in attributes:
                    self.ids.append(attributes['id'])
                if tag in ('input', 'select'):
                    self.controls.append(attributes['id'])
                if tag == 'label':
                    self.labels.append(attributes['for'])
        parser = Parser()
        parser.feed((ROOT / 'ui/index.html').read_text())
        self.assertEqual(len(parser.ids), len(set(parser.ids)))
        self.assertTrue(set(parser.controls) <= set(parser.labels))


if __name__ == '__main__':
    unittest.main()
