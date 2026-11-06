"""Voltage sweeps and temperature trips with limits and fail-safe shutdown."""
import time

from .bench import finite, utc_now
from .report import Report


def nonnegative(value, name):
    value = finite(value, name)
    if value < 0:
        raise ValueError(f'{name} must be nonnegative')
    return value


def voltage(value):
    value = finite(value, 'voltage')
    if not 0 <= value <= 5:
        raise ValueError('voltage must be between 0 and 5 V')
    return value


def samples(values, name):
    values = list(values)
    if not 1 <= len(values) <= 10000:
        raise ValueError(f'{name} must contain 1 to 10000 samples')
    return [finite(value, name) for value in values]


def _run(bench, root, kind, settings, read_samples):
    report = Report(root, kind, settings)
    first_event = len(bench.transcript)
    status, error, shutdown = 'PASS', '', False
    try:
        report.metadata['instruments'] = {
            name: bench.query(name, '*IDN?') for name in ('supply', 'dmm', 'scope')}
        bench.set_voltage(settings.get('voltage', settings.get('voltages', [0])[0]))
        bench.output(True)
        for row in read_samples():
            report.append(row)
            if row['status'] == 'FAIL':
                status = 'FAIL'
                if kind == 'soak':
                    break
    except Exception as exc:
        status, error = 'ERROR', f'{type(exc).__name__}: {exc}'
    except BaseException as exc:
        status, error = 'ERROR', f'Interrupted: {type(exc).__name__}'
        raise
    finally:
        try:
            bench.output(False)
            shutdown = bench.query('supply', 'OUTP?') == '0'
            if not shutdown:
                raise RuntimeError('supply output did not switch off')
        except Exception as exc:
            status = 'ERROR'
            error += f' Shutdown failed: {exc}'
        result = report.finish(status, error, bench.transcript[first_event:], shutdown)
    return result


def run_sweep(bench, root, voltages, tolerance=0.11, settle=0):
    """Check DMM DC voltage and scope amplitude against an absolute V limit."""
    points = [voltage(value) for value in samples(voltages, 'voltages')]
    tolerance = nonnegative(tolerance, 'tolerance')
    settle = nonnegative(settle, 'settle')

    def readings():
        started = time.monotonic()
        for point in points:
            bench.set_voltage(point)
            time.sleep(settle)
            dmm = bench.measure('dmm', 'MEAS:VOLT:DC?')
            scope = bench.measure('scope', 'MEAS:VAMP?')
            frequency = bench.measure('scope', 'MEAS:FREQ?')
            passed = abs(dmm - point) <= tolerance and abs(scope - point) <= tolerance
            yield dict(timestamp_utc=utc_now(), elapsed_s=round(time.monotonic()-started, 6),
                       set_voltage_v=point, dmm_v=dmm, scope_v=scope,
                       frequency_hz=frequency, status='PASS' if passed else 'FAIL')

    return _run(bench, root, 'sweep', dict(voltages=points, tolerance=tolerance,
                                        settle=settle), readings)


def run_soak(bench, root, temperatures, low=20, high=60, voltage=3.3, interval=0):
    """Read one temperature per profile point and stop at the first trip."""
    points = samples(temperatures, 'temperatures')
    low, high = finite(low, 'low'), finite(high, 'high')
    if low > high:
        raise ValueError('low temperature limit must not exceed high')
    # The argument name stays convenient at the public API boundary.
    supply_voltage = finite(voltage, 'voltage')
    if not 0 <= supply_voltage <= 5:
        raise ValueError('voltage must be between 0 and 5 V')
    interval = nonnegative(interval, 'interval')

    def readings():
        started = time.monotonic()
        for index, temperature in enumerate(points):
            if index:
                time.sleep(interval)
            bench.set_temperature(temperature)
            measured = bench.measure('dmm', 'MEAS:TEMP?')
            yield dict(timestamp_utc=utc_now(), elapsed_s=round(time.monotonic()-started, 6),
                       set_voltage_v=supply_voltage, temperature_c=measured,
                       status='PASS' if low <= measured <= high else 'FAIL')

    return _run(bench, root, 'soak', dict(temperatures=points, low=low, high=high,
                                       voltage=supply_voltage, interval=interval), readings)
