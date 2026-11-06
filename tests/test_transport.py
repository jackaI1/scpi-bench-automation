from pathlib import Path
import socket
import subprocess
import sys
import threading
from contextlib import contextmanager

import pytest

from scpi_bench.bench import SimBench
from scpi_bench.server import running_server

ROOT = Path(__file__).resolve().parents[1]
CLIENTS = [('tclsh', ROOT / 'wrappers/scpi.tcl'), ('perl', ROOT / 'wrappers/scpi.pl')]


def client(executable, script, port, *commands):
    return subprocess.run([executable, str(script), '127.0.0.1', str(port), *commands],
                          text=True, capture_output=True, timeout=8)


@pytest.mark.parametrize('executable,script', CLIENTS)
@pytest.mark.parametrize('instrument,commands,expected', [
    ('supply', ['VOLT 2.5', 'OUTP ON', 'VOLT?', 'OUTP?', 'OUTP OFF', 'OUTP?'],
     ['2.500000', '1', '0']),
    ('dmm', ['MEAS:VOLT:DC?', 'MEAS:TEMP?'], ['3.306600', '25.000000']),
    ('scope', ['MEAS:VAMP?', 'MEAS:FREQ?'], ['3.234000', '1000.0']),
])
def test_actual_wrappers_drive_visa_backed_tcp_server(executable, script, instrument,
                                                    commands, expected):
    with SimBench() as bench:
        bench.set_voltage(3.3)
        bench.output(True)
        with running_server(bench, instrument) as server:
            port = server.server_address[1]
            result = client(executable, script, port, '*IDN?', *commands)
            assert result.returncode == 0, result.stderr
            assert result.stdout.splitlines()[1:] == expected
            assert f'SIM-{instrument.upper()}' in result.stdout
        with socket.socket() as probe:
            assert probe.connect_ex(('127.0.0.1', port)) != 0
        assert bench.query('supply', 'OUTP?') == '0'


@pytest.mark.parametrize('executable,script', CLIENTS)
def test_wrappers_fail_on_invalid_command(executable, script):
    with SimBench() as bench, running_server(bench, 'supply') as server:
        result = client(executable, script, server.server_address[1], 'BOGUS?')
        assert result.returncode != 0
        assert 'ERROR' in result.stderr


def test_server_rejects_unsafe_voltage_without_changing_output():
    with SimBench() as bench, running_server(bench, 'supply') as server:
        with socket.create_connection(server.server_address, timeout=2) as sock:
            sock.sendall(b'VOLT 12\n')
            assert sock.recv(1024).startswith(b'ERROR')
        assert bench.query('supply', 'VOLT?') == '0.000000'


@contextmanager
def silent_peer():
    # Owned by this pytest process. The context closes both accepted and listening sockets.
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        listener.listen()
        listener.settimeout(5)
        stop = threading.Event()

        def serve():
            try:
                conn, _ = listener.accept()
                with conn:
                    stop.wait(4)
            except OSError:
                pass

        thread = threading.Thread(target=serve)
        thread.start()
        try:
            yield listener.getsockname()[1]
        finally:
            stop.set()
            thread.join(timeout=6)
            assert not thread.is_alive()


@pytest.mark.parametrize('executable,script', CLIENTS)
def test_clients_timeout_instead_of_hanging(executable, script):
    with silent_peer() as port:
        result = client(executable, script, port, '*IDN?')
        assert result.returncode != 0
        assert 'tim' in result.stderr.lower()


@pytest.mark.parametrize('arguments,code,status,samples', [
    (['sweep'], 0, 'PASS', 6),
    (['sweep', '--voltages', '1', '2', '--tolerance', '0.001'], 1, 'FAIL', 2),
    (['soak', '--temperatures', '25', '65', '30'], 1, 'FAIL', 2),
    (['soak'], 0, 'PASS', 3),
])
def test_cli_status_and_reports(tmp_path, arguments, code, status, samples):
    import csv
    import json
    result = subprocess.run([sys.executable, '-m', 'scpi_bench', *arguments,
                             '--output', str(tmp_path)], text=True, capture_output=True,
                            timeout=10)
    assert result.returncode == code, result.stderr
    assert status in result.stdout
    report_dir, = tmp_path.iterdir()
    metadata = json.loads((report_dir / 'run.json').read_text())
    assert metadata['status'] == status
    with (report_dir / 'measurements.csv').open() as stream:
        assert len(list(csv.DictReader(stream))) == samples


def test_cli_rejects_invalid_input(tmp_path):
    result = subprocess.run([sys.executable, '-m', 'scpi_bench', 'sweep',
                             '--voltages', 'nan', '--output', str(tmp_path)],
                            text=True, capture_output=True, timeout=5)
    assert result.returncode == 2
    assert 'finite' in result.stderr
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('executable,script', CLIENTS)
def test_clients_confirm_writes_and_reject_bad_write_values(executable, script):
    with SimBench() as bench, running_server(bench, 'supply') as server:
        port = server.server_address[1]
        bad = client(executable, script, port, 'VOLT 9')
        assert bad.returncode != 0
        assert 'ERROR' in bad.stderr
        good = client(executable, script, port, 'VOLT 1.25')
        assert good.returncode == 0, good.stderr
        assert bench.query('supply', 'VOLT?') == '1.250000'
