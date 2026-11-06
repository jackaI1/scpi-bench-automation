"""Loopback-only, newline SCPI bridge to one PyVISA simulated instrument."""
from contextlib import contextmanager
from functools import lru_cache
import json
import os
import socket
import socketserver
import subprocess
import sys
import threading


@lru_cache(maxsize=1)
def process_start():
    return subprocess.check_output(['ps', '-p', str(os.getpid()), '-o', 'lstart='],
                                   text=True).strip()


def dispatch(bench, instrument, command):
    command = command.strip().upper().lstrip(':')
    queries = {
        'supply': {'*IDN?', '*OPC?', 'VOLT?', 'OUTP?'},
        'dmm': {'*IDN?', '*OPC?', 'MEAS:VOLT:DC?', 'MEAS:TEMP?'},
        'scope': {'*IDN?', '*OPC?', 'MEAS:VAMP?', 'MEAS:FREQ?'},
    }
    if command in queries[instrument]:
        return bench.query(instrument, command)
    parts = command.split()
    if instrument == 'supply' and len(parts) == 2:
        name, value = parts
        if name == 'VOLT':
            bench.set_voltage(value)
            return None
        if name == 'OUTP' and value in ('0', '1', 'ON', 'OFF'):
            bench.output(value in ('1', 'ON'))
            return None
    raise ValueError('unsupported command or value')


@contextmanager
def running_server(bench, instrument='supply', port=0):
    """Serve until context exit; close the exact listener/thread and disable output."""
    if instrument not in ('supply', 'dmm', 'scope'):
        raise ValueError('unknown instrument')

    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            self.connection.settimeout(1)
            try:
                while True:
                    line = self.rfile.readline(4097)
                    if not line:
                        return
                    if len(line) > 4096 or not line.endswith(b'\n'):
                        self.wfile.write(b'ERROR: line too long or unterminated\n')
                        return
                    try:
                        reply = dispatch(bench, instrument, line.decode('ascii'))
                    except (ValueError, UnicodeError) as error:
                        reply = f'ERROR: {error}'
                    except Exception as error:
                        reply = f'ERROR: instrument failure ({type(error).__name__})'
                    if reply is not None:
                        self.wfile.write((reply + '\n').encode('ascii'))
            except (socket.timeout, ConnectionError, OSError):
                return

    with socketserver.TCPServer(('127.0.0.1', port), Handler) as server:
        thread = threading.Thread(target=server.serve_forever,
                                  kwargs={'poll_interval': 0.05}, name='scpi-loopback')
        server.ownership = dict(owner='scpi-bench context', pid=os.getpid(),
                                process_start=process_start(), host='127.0.0.1',
                                port=server.server_address[1], instrument=instrument,
                                cleanup='context exit: shutdown, join, server_close; CLI: Ctrl-C')
        print(json.dumps(server.ownership), file=sys.stderr, flush=True)
        thread.start()
        try:
            yield server
        finally:
            server.shutdown()
            thread.join(timeout=3)
            if thread.is_alive():
                raise RuntimeError('SCPI server thread failed to stop')
            bench.output(False)
