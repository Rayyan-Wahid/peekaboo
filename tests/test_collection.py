import csv
import io
import socket
import threading
import unittest
from unittest.mock import patch

from peekaboo.collect import sites_from, Proxy, review_reasons


class ManifestValidation(unittest.TestCase):
    def check_rows(self, rows):
        content = io.StringIO()
        writer = csv.writer(content)
        writer.writerow(['site_id', 'url'])
        writer.writerows(rows)
        content.seek(0)
        with patch('builtins.open', return_value=content):
            return sites_from('sites.csv')

    def test_duplicate_ids_rejected(self):
        with self.assertRaises(ValueError):
            self.check_rows([['x', 'https://example.org'], ['x', 'https://example.com']])

    def test_plaintext_site_rejected(self):
        with self.assertRaises(ValueError):
            self.check_rows([['x', 'http://example.org']])

    def test_https_manifest_accepted(self):
        self.assertEqual(self.check_rows([['x', 'https://example.org']])[0]['site_id'], 'x')


class QualityChecks(unittest.TestCase):
    def record(self, code=200):
        return dict(navigation={'responseStatus': code}, tls_frames=50,
                    body_chars=500, final_url='https://example.org/', title='Example')

    def test_browser_navigation_failure_rejected_despite_tls(self):
        self.assertIn('missing_or_unsuccessful_http_response', review_reasons(self.record(0)))

    def test_http_error_rejected(self):
        self.assertIn('missing_or_unsuccessful_http_response', review_reasons(self.record(503)))

    def test_browser_error_dom_rejected(self):
        self.assertIn('browser_error_page', review_reasons(dict(self.record(), browser_error_page=True)))

    def test_good_visit_is_candidate(self):
        self.assertEqual(review_reasons(self.record()), [])


class TunnelTests(unittest.TestCase):
    def test_upstream_failure_is_logged(self):
        proxy = Proxy()
        threading.Thread(target=proxy.serve_forever, daemon=True).start()
        client = socket.create_connection(proxy.server_address, timeout=3)
        try:
            with patch('peekaboo.collect.socket.create_connection', side_effect=TimeoutError('test timeout')):
                client.sendall(b'CONNECT example.org:443 HTTP/1.1\r\n\r\n')
                self.assertEqual(client.recv(4096), b'')
                event = proxy.events.get_nowait()
                self.assertEqual(event['phase'], 'upstream_connect')
                self.assertEqual(event['type'], 'TimeoutError')
        finally:
            client.close()
            proxy.stopping.set()
            proxy.shutdown()
            proxy.server_close()

    def test_connect_forwards_bytes_unchanged(self):
        proxy = Proxy()
        threading.Thread(target=proxy.serve_forever, daemon=True).start()
        upstream, peer = socket.socketpair()
        client = socket.create_connection(proxy.server_address, timeout=3)
        peer.settimeout(3)
        try:
            with patch('peekaboo.collect.socket.create_connection', return_value=upstream):
                client.sendall(b'CONNECT example.org:443 HTTP/1.1\r\n\r\n')
                self.assertIn(b'200 Connection Established', client.recv(4096))
                client.sendall(b'\x16\x03\x03opaque-client-data')
                self.assertEqual(peer.recv(4096), b'\x16\x03\x03opaque-client-data')
                peer.sendall(b'opaque-server-data')
                self.assertEqual(client.recv(4096), b'opaque-server-data')
        finally:
            client.close()
            peer.close()
            proxy.stopping.set()
            proxy.shutdown()
            proxy.server_close()


if __name__ == '__main__':
    unittest.main()
