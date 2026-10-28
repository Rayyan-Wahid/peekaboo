"""Controlled HTTPS collection through a dedicated loopback CONNECT tunnel.

TLS is forwarded unchanged. This is a lab proxy dataset, not a Wi-Fi wire trace.
"""
import csv
import hashlib
import json
import random
import select
import shutil
import socket
import socketserver
import subprocess
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit


def executable(name):
    found = shutil.which(name)
    candidate = Path('C:/Program Files/Wireshark') / (name + '.exe')
    return found or (str(candidate) if candidate.exists() else None)


class Tunnel(socketserver.BaseRequestHandler):
    def handle(self):
        upstream = None
        try:
            self.request.settimeout(15)
            header = b''
            while b'\r\n\r\n' not in header and len(header) < 16384:
                chunk = self.request.recv(4096)
                if not chunk:
                    return
                header += chunk
            first, rest = header.split(b'\r\n\r\n', 1)
            method, authority, _ = first.split(b'\r\n', 1)[0].decode('ascii').split()
            if method != 'CONNECT':
                self.request.sendall(b'HTTP/1.1 405 Method Not Allowed\r\nContent-Length: 0\r\n\r\n')
                return
            host, port = authority.rsplit(':', 1)
            if port != '443':
                return
            upstream = socket.create_connection((host.strip('[]'), int(port)), timeout=15)
            self.request.sendall(b'HTTP/1.1 200 Connection Established\r\n\r\n')
            if rest:
                upstream.sendall(rest)
            self.request.settimeout(None)
            upstream.settimeout(None)
            while True:
                readable, _, _ = select.select([self.request, upstream], [], [], 2)
                if self.server.stopping.is_set():
                    break
                for source in readable:
                    data = source.recv(65536)
                    if not data:
                        return
                    (upstream if source is self.request else self.request).sendall(data)
        except (OSError, ValueError):
            pass
        finally:
            if upstream:
                upstream.close()


class Proxy(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self):
        self.stopping = threading.Event()
        super().__init__(('127.0.0.1', 0), Tunnel)


def sites_from(path):
    with open(path, newline='', encoding='utf-8') as f:
        sites = list(csv.DictReader(f))
    ids = set()
    for site in sites:
        if not site['site_id'] or site['site_id'] in ids:
            raise ValueError('Site IDs must be nonempty and unique')
        if urlsplit(site['url']).scheme != 'https':
            raise ValueError('Only HTTPS site URLs are supported')
        ids.add(site['site_id'])
    if not sites:
        raise ValueError('Site manifest is empty')
    return sites


def collect(args):
    from selenium import webdriver
    from selenium.common.exceptions import SessionNotCreatedException, NoSuchDriverException
    from selenium.webdriver.chrome.service import Service
    dumpcap, tshark = executable('dumpcap'), executable('tshark')
    if not dumpcap or not tshark:
        raise RuntimeError('Install Wireshark with dumpcap and tshark first')
    if args.seconds < 5 or args.visits < 1 or args.pause < 0:
        raise ValueError('seconds >= 5, visits >= 1, and pause >= 0 required')
    sites = sites_from(args.sites)
    if args.limit:
        sites = sites[:args.limit]
    session = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6]
    folder = Path(args.output) / session
    folder.mkdir(parents=True, exist_ok=False)
    order = [(site, repeat) for repeat in range(args.visits) for site in sites]
    random.Random(args.seed).shuffle(order)
    config = dict(vars(args), session_id=session, scope='loopback CONNECT proxy, TCP only',
                  cache_policy='fresh browser profile per visit', sites=sites,
                  dumpcap_version=subprocess.check_output([dumpcap, '--version'], text=True).splitlines()[0])
    (folder / 'session.json').write_text(json.dumps(config, indent=2), encoding='utf-8')
    print(f'Session: {folder}', flush=True)
    candidate_count = 0
    for index, (site, repeat) in enumerate(order):
        visit_id = uuid.uuid4().hex
        capture = folder / (visit_id + '.pcapng')
        record = dict(session_id=session, visit_id=visit_id, site_id=site['site_id'],
                      url=site['url'], repeat=repeat, condition='baseline', capture=capture.name,
                      started_utc=datetime.now(timezone.utc).isoformat(), status='failed')
        proxy = Proxy()
        threading.Thread(target=proxy.serve_forever, daemon=True).start()
        port = proxy.server_address[1]
        record['proxy_port'] = port
        driver = process = None
        fatal_startup = False
        with (folder / (visit_id + '.capture.log')).open('w', encoding='utf-8') as log:
            try:
                options = webdriver.ChromeOptions()
                profile = Path('.cache/profiles') / visit_id
                profile.mkdir(parents=True, exist_ok=False)
                options.add_argument('--user-data-dir=' + str(profile.resolve()))
                options.add_argument('--headless=new')
                options.add_argument('--disable-quic')
                options.add_argument('--disable-background-networking')
                options.add_argument('--no-first-run')
                options.add_argument('--window-size=1365,768')
                options.add_experimental_option('prefs', {
                    'safebrowsing.enabled': True,
                    'profile.default_content_setting_values.geolocation': 2,
                    'profile.default_content_setting_values.notifications': 2,
                })
                options.add_argument(f'--proxy-server=http://127.0.0.1:{port}')
                options.page_load_strategy = 'none'
                service = Service(executable_path=args.driver, service_args=['--verbose'],
                                  log_output=str(folder / (visit_id + '.driver.log')))
                driver = webdriver.Chrome(service=service, options=options)
                record['browser_version'] = driver.capabilities['browserVersion']
                driver.execute_cdp_cmd('Network.enable', {})
                driver.execute_cdp_cmd('Network.setCacheDisabled', {'cacheDisabled': True})
                process = subprocess.Popen([dumpcap, '-i', args.interface, '-f',
                    f'tcp port {port}', '-a', f'duration:{args.seconds + 2}', '-w', str(capture)],
                    stdout=log, stderr=log)
                time.sleep(1)
                if process.poll() is not None:
                    raise RuntimeError('Capture failed to start; inspect capture log')
                start = time.monotonic()
                driver.get(site['url'])
                time.sleep(max(0, args.seconds - (time.monotonic() - start)))
                record['final_url'] = driver.current_url
                record['title'] = driver.title
                record['ready_state'] = driver.execute_script('return document.readyState')
                record['body_chars'] = driver.execute_script('return document.body ? document.body.innerText.length : 0')
                record['navigation'] = driver.execute_script('return performance.getEntriesByType("navigation")[0]?.toJSON() || {}')
                process.wait(timeout=10)
                if process.returncode:
                    raise RuntimeError('Capture exited with error')
                tls = subprocess.check_output([tshark, '-r', str(capture), '-Y', 'tls',
                    '-T', 'fields', '-e', 'frame.number'], text=True, timeout=30)
                record['tls_frames'] = len(tls.splitlines())
                record['sha256'] = hashlib.sha256(capture.read_bytes()).hexdigest()
                title = record['title'].lower()
                blocked = any(x in title for x in ['just a moment', 'access denied', 'captcha', 'privacy error'])
                if record['tls_frames'] < 5 or record['body_chars'] < 50 or blocked or not record['final_url'].startswith('https://'):
                    record['status'] = 'needs_review'
                else:
                    record['status'] = 'candidate'
                driver.save_screenshot(str(folder / (visit_id + '.png')))
            except Exception as error:
                record['status'] = 'failed'
                fatal_startup = isinstance(error, (SessionNotCreatedException, NoSuchDriverException))
                record['error'] = f'{type(error).__name__}: {error}'[:2000]
            finally:
                if process and process.poll() is None:
                    try:
                        process.terminate()
                        process.wait(timeout=10)
                    except (OSError, subprocess.TimeoutExpired) as error:
                        record['capture_cleanup_error'] = str(error)
                if driver:
                    try:
                        driver.quit()
                    except Exception as error:
                        record['browser_cleanup_error'] = str(error)
                proxy.stopping.set()
                proxy.shutdown()
                proxy.server_close()
                with (folder / 'manifest.jsonl').open('a', encoding='utf-8') as f:
                    f.write(json.dumps(record) + '\n')
        print(f'{index+1}/{len(order)} {site["site_id"]}: {record["status"]} {record.get("error", "").splitlines()[0] if record.get("error") else ""}', flush=True)
        candidate_count += record['status'] == 'candidate'
        if fatal_startup:
            print('Browser startup failed. Stopping this session; inspect the driver log. No retry loop.', flush=True)
            return 1
        if index < len(order) - 1:
            time.sleep(args.pause)
    print('Collection finished. Review screenshots and manifests before accepting traces.', flush=True)
    return 0 if candidate_count == len(order) else 1
