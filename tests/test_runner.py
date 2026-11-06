import csv
import json
import math

import pytest

from scpi_bench.bench import SimBench
from scpi_bench.runner import run_soak, run_sweep


def read_rows(result):
    with (result.path / 'measurements.csv').open() as stream:
        return list(csv.DictReader(stream))


def test_sweep_records_real_readings_reports_and_shutdown(tmp_path):
    with SimBench() as bench:
        result = run_sweep(bench, tmp_path, [0, 2.5, 5])
        assert result.status == 'PASS'
        rows = read_rows(result)
        assert [float(row['dmm_v']) for row in rows] == [0, 2.505, 5.01]
        assert [float(row['scope_v']) for row in rows] == [0, 2.45, 4.9]
        assert all(row['timestamp_utc'].endswith('+00:00') for row in rows)
        assert [row['status'] for row in rows] == ['PASS'] * 3
        assert bench.query('supply', 'OUTP?') == '0'
        meta = json.loads((result.path / 'run.json').read_text())
        assert meta['settings']['voltages'] == [0, 2.5, 5]
        assert 'SIM-DMM' in meta['instruments']['dmm']
        assert meta['status'] == 'PASS'
        html = (result.path / 'report.html').read_text()
        assert '<table>' in html and '4.9' in html and 'PASS' in html
        transcript = (result.path / 'scpi.csv').read_text()
        assert 'MEAS:VOLT:DC?' in transcript and 'MEAS:VAMP?' in transcript
        assert 'OUTP 0' in transcript


def test_tight_limits_fail_without_discarding_measurements(tmp_path):
    with SimBench() as bench:
        result = run_sweep(bench, tmp_path, [1, 2, 3], tolerance=0.01)
        assert result.status == 'FAIL'
        assert len(read_rows(result)) == 3
        assert {row['status'] for row in read_rows(result)} == {'FAIL'}
        assert bench.query('supply', 'OUTP?') == '0'


def test_soak_stops_at_first_temperature_outside_inclusive_limits(tmp_path):
    with SimBench() as bench:
        result = run_soak(bench, tmp_path, [20, 60, 61, 25], low=20, high=60)
        assert result.status == 'FAIL'
        rows = read_rows(result)
        assert [float(row['temperature_c']) for row in rows] == [20, 60, 61]
        assert [row['status'] for row in rows] == ['PASS', 'PASS', 'FAIL']
        assert bench.query('supply', 'OUTP?') == '0'
        assert '61' in (result.path / 'report.html').read_text()


def test_soak_passes_and_honors_sample_interval(tmp_path):
    with SimBench() as bench:
        result = run_soak(bench, tmp_path, [25, 26, 27], interval=0.01)
        assert result.status == 'PASS'
        rows = read_rows(result)
        assert float(rows[-1]['elapsed_s']) >= 0.02
        assert len(rows) == 3


@pytest.mark.parametrize('kwargs', [
    {'voltages': []}, {'voltages': [math.nan]}, {'voltages': [6]},
    {'voltages': [1], 'tolerance': -1}, {'voltages': [1], 'settle': math.inf},
])
def test_bad_sweep_configuration_never_enables_output(tmp_path, kwargs):
    with SimBench() as bench:
        with pytest.raises(ValueError):
            run_sweep(bench, tmp_path, **kwargs)
        assert not any(row['command'] == 'OUTP 1' for row in bench.transcript)
        assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('kwargs', [
    {'temperatures': []}, {'temperatures': [math.inf]},
    {'temperatures': [25], 'low': 60, 'high': 20},
    {'temperatures': [25], 'interval': -1},
    {'temperatures': [25], 'voltage': 6},
])
def test_bad_soak_configuration_never_enables_output(tmp_path, kwargs):
    with SimBench() as bench:
        with pytest.raises(ValueError):
            run_soak(bench, tmp_path, **kwargs)
        assert not any(row['command'] == 'OUTP 1' for row in bench.transcript)


def test_real_visa_timeout_keeps_partial_report_and_turns_output_off(tmp_path, monkeypatch):
    with SimBench() as bench:
        original = bench.measure
        count = 0

        def missing_response(device, command):
            nonlocal count
            if command == 'MEAS:VAMP?':
                count += 1
                if count == 2:
                    # Query a write-only fixture command: real simulator read timeout.
                    return original(device, 'SIM:INPUT 1.000000')
            return original(device, command)

        monkeypatch.setattr(bench, 'measure', missing_response)
        result = run_sweep(bench, tmp_path, [1, 2, 3])
        assert result.status == 'ERROR'
        assert len(read_rows(result)) == 1
        assert 'VI_ERROR_TMO' in (result.path / 'run.json').read_text()
        assert bench.query('supply', 'OUTP?') == '0'


def test_reports_do_not_overwrite_previous_runs(tmp_path):
    with SimBench() as bench:
        first = run_sweep(bench, tmp_path, [1])
        second = run_sweep(bench, tmp_path, [1])
        assert first.path != second.path
        assert (first.path / 'report.html').exists()
        assert (second.path / 'report.html').exists()
