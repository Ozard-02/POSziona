"""
Thermal receipt printing for Posziona (ESC/POS, stdlib only).

Design: the POS already builds receipt *text* in the browser
(`buildReceipt` in pos.js, incl. kitchen slips). The server only
converts that text to ESC/POS bytes and pushes them to the device —
no receipt-layout duplication, no new dependencies (matters for the
frozen binary: python-escpos/pyusb would need system libusb too).

Transports (all plain byte sinks), selected by printer_path:
- /dev/usb/lp*  — USB printers claimed by the usblp kernel driver.
- /dev/ttyUSB* / /dev/ttyS* / COM ports — serial printers / USB-serial
  adapters (baud via termios on POSIX, pyserial on Windows).
- socket:HOST[:PORT] — network printers (Ethernet/Wi-Fi, 9100 default).
  Stdlib TCP, all platforms.
- win32:Name — Windows spooler RAW passthrough to a print queue
  (USB printers via their installed queue). Needs pywin32.
- 'auto' — first existing device (USB preferred; Windows: first COM).
- any other path — opened as a plain file (also how tests fake a
  printer: point printer_path at a temp file and read back the bytes).

Text is sanitized to 7-bit ASCII (€ → 'EUR', accented vowels → base
letter): deterministic on every ESC/POS model regardless of its
default code page — no codepage commands needed.
"""
import glob
import os

from app.services.settings_service import get_effective_settings
from app.utils.logger import get_logger

logger = get_logger('services.printer')

ESC = b'\x1b'
GS = b'\x1d'

DEFAULT_COLS = 42
DEFAULT_BAUD = 9600
VALID_BAUDS = (1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200)

# Beyond ASCII + a few printable symbols, map to safe replacements.
_ACCENTS = {
    'à': 'a', 'á': 'a', 'â': 'a', 'ä': 'a',
    'è': 'e', 'é': 'e', 'ê': 'e', 'ë': 'e',
    'ì': 'i', 'í': 'i', 'î': 'i', 'ï': 'i',
    'ò': 'o', 'ó': 'o', 'ô': 'o', 'ö': 'o',
    'ù': 'u', 'ú': 'u', 'û': 'u', 'ü': 'u',
    'ý': 'y', 'ÿ': 'y', 'ñ': 'n', 'ç': 'c',
    'À': 'A', 'Á': 'A', 'Â': 'A', 'Ä': 'A',
    'È': 'E', 'É': 'E', 'Ê': 'E', 'Ë': 'E',
    'Ì': 'I', 'Í': 'I', 'Î': 'I', 'Ï': 'I',
    'Ò': 'O', 'Ó': 'O', 'Ô': 'O', 'Ö': 'O',
    'Ù': 'U', 'Ú': 'U', 'Û': 'U', 'Ü': 'U',
    'Ý': 'Y', 'Ñ': 'N', 'Ç': 'C',
    '€': 'EUR', '£': 'GBP', '°': 'o',
    '—': '-', '–': '-', '«': '"', '»': '"',
}


def sanitize_line(line, cols):
    """Make one line printer-safe: ASCII, truncated to cols."""
    out = []
    for ch in str(line):
        if ord(ch) < 128 and ch not in '\r':
            out.append(ch)
        elif ch in _ACCENTS:
            out.append(_ACCENTS[ch])
        elif ch == '\n':
            out.append(ch)
        # other codepoints dropped (box-drawing, emoji, ...)
    text = ''.join(out).replace('\t', ' ')
    return '\n'.join(part[:cols] for part in text.split('\n'))


def build_bytes(text, cols=DEFAULT_COLS, cut=True):
    """Wrap receipt text in a minimal ESC/POS envelope.

    ESC @ (init) + left-aligned text + feed + optional partial cut.
    A form-feed char (\\f) inside the text is a cut marker: the printer
    cuts there and continues (section slips, then the total recap).
    With cut=False the markers become plain feeds instead.
    No codepage / font commands: works on any default configuration.
    """
    data = bytearray()
    data += ESC + b'@'          # init
    data += ESC + b'a\x00'      # left align
    parts = str(text).split('\f')
    for part in parts:
        for raw_line in part.split('\n'):
            for chunk in sanitize_line(raw_line, cols).split('\n'):
                data += chunk.encode('ascii') + b'\n'
        data += ESC + b'd\x04'  # feed 4 lines
        if cut:
            data += GS + b'V\x01'   # partial cut (also after last part)
    return bytes(data)


def build_test_ticket(cols=DEFAULT_COLS):
    """Sample ticket (also exercises accent/€ sanitizing)."""
    sep = '=' * min(cols, 32)
    return '\n'.join([
        sep,
        'Posziona - prova stampa',
        'TOTALE: EUR 12,50',
        'Grazie e arrivederci!',
        sep,
    ])


def _setting_int(settings, key, default):
    try:
        return int(settings.get(key, default) or default)
    except (TypeError, ValueError):
        return default


def resolve_device(db_name):
    """Return (path, baud, cols, cut) from party settings.

    printer_path ''/missing = printing disabled (browser fallback).
    'auto' probes /dev/usb/lp* then /dev/ttyUSB*.
    Raises ValueError on bad configuration.
    """
    settings = get_effective_settings(db_name)
    # Tolerate quote-paste ('auto' typed as ''auto'' etc.): paths never
    # legitimately start/end with quotes.
    raw_path = (settings.get('printer_path') or '').strip().strip('\'"').strip()
    if not raw_path:
        raise ValueError('No printer configured (printer_path is empty)')
    baud = _setting_int(settings, 'printer_baud', DEFAULT_BAUD)
    if baud not in VALID_BAUDS:
        raise ValueError(f'Unsupported baud rate: {baud}')
    cols = _setting_int(settings, 'printer_cols', DEFAULT_COLS)
    if not 16 <= cols <= 64:
        raise ValueError(f'Bad printer_cols: {cols}')
    cut = str(settings.get('printer_cut', '1')) == '1'

    if raw_path == 'auto':
        import sys
        if sys.platform == 'win32':
            coms = list_windows_com_ports()
            if coms:
                return 'serial:' + coms[0], baud, cols, cut
            raise ValueError(
                'No COM printers found; USB queues need win32:<name> '
                '(see printer/status for installed queues)')
        for pattern in ('/dev/usb/lp*', '/dev/ttyUSB*', '/dev/ttyACM*', '/dev/ttyS*'):
            candidates = sorted(glob.glob(pattern))
            if candidates:
                return candidates[0], baud, cols, cut
        raise ValueError('No printer found (probed /dev/usb/lp*, /dev/ttyUSB*, /dev/ttyACM*, /dev/ttyS*)')
    return raw_path, baud, cols, cut


def _open_serial(path, baud):
    """Open a serial device at baud, 8N1 raw.

    Linux/macOS: termios (stdlib). Windows COM ports: pyserial
    (optional dependency, imported lazily).
    """
    import sys
    if sys.platform == 'win32':
        return _open_serial_pyserial(path, baud)
    return _open_serial_termios(path, baud)


def _open_serial_termios(path, baud):
    """POSIX serial open (also used by detect_serial for reading)."""
    try:
        import termios
    except ImportError:
        raise RuntimeError('Serial printers need Linux/macOS or pyserial')
    const = getattr(termios, f'B{baud}', None)
    if const is None:
        raise ValueError(f'Unsupported baud rate: {baud}')
    try:
        fd = os.open(path, os.O_RDWR | os.O_NOCTTY)
    except OSError as e:
        raise RuntimeError(f'Cannot open {path}: {e.strerror or e}')
    try:
        attrs = termios.tcgetattr(fd)
        attrs[4] = const  # ispeed
        attrs[5] = const  # ospeed
        attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL  # 8N1
        attrs[0] &= ~(termios.IGNBRK | termios.BRKINT | termios.IGNPAR |
                      termios.PARMRK | termios.INPCK | termios.ISTRIP |
                      termios.INLCR | termios.IGNCR | termios.ICRNL |
                      termios.IXON)
        attrs[1] &= ~termios.OPOST  # raw output, no \n → \r\n mangling
        attrs[3] &= ~(termios.ECHO | termios.ECHONL | termios.ICANON |
                      termios.ISIG | termios.IEXTEN)
        attrs[6][termios.VMIN] = 0
        attrs[6][termios.VTIME] = 0
        termios.tcsetattr(fd, termios.TCSANOW, attrs)
    except (OSError, termios.error) as e:
        os.close(fd)
        raise RuntimeError(f'Cannot configure {path}: {e}')
    return os.fdopen(fd, 'wb')


def _open_serial_pyserial(path, baud):
    """COM port via pyserial (Windows; also fallback anywhere)."""
    try:
        import serial
    except ImportError:
        raise RuntimeError(
            'COM ports need the pyserial package: pip install pyserial')
    try:
        ser = serial.Serial(path, baudrate=baud, bytesize=8,
                            parity='N', stopbits=1, timeout=2,
                            write_timeout=5)
    except Exception as e:
        raise RuntimeError(f'Cannot open {path}: {e}')

    class _SerSink:
        def __init__(self, ser):
            self._ser = ser

        def write(self, data):
            self._ser.write(data)

        def flush(self):
            self._ser.flush()

        def close(self):
            try:
                self._ser.close()
            except Exception:
                pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self.close()

    return _SerSink(ser)


DETECT_BAUDS = (9600, 19200, 38400, 57600, 115200)


def detect_serial(path, bauds=DETECT_BAUDS, timeout=0.6):
    """Find the baud rate of an ESC/POS serial printer, or None.

    Sends DLE EOT (real-time status request) at each baud and waits for
    the 1-byte reply. Open/config failures raise immediately (wrong
    permissions etc. won't heal at another baud); silence tries the next.
    """
    import sys
    if sys.platform == 'win32':
        return _detect_serial_pyserial(path, bauds, timeout)
    import select
    for baud in bauds:
        try:
            fh = _open_serial_termios(path, baud)
        except ValueError:
            raise
        except RuntimeError:
            raise  # systematic (permissions, missing device, not Linux)
        try:
            fh.write(b'\x10\x04\x01')  # DLE EOT n=1: paper-sensor status
            fh.flush()
            ready, _, _ = select.select([fh.fileno()], [], [], timeout)
            if ready:
                reply = os.read(fh.fileno(), 8)
                if len(reply) == 1:
                    logger.info(f"Serial printer on {path} answers at {baud}")
                    return baud
        except OSError:
            pass
        finally:
            fh.close()
    return None


def _detect_serial_pyserial(path, bauds, timeout):
    """DLE EOT probe over pyserial (Windows COM ports)."""
    try:
        import serial
    except ImportError:
        raise RuntimeError(
            'COM detection needs the pyserial package: pip install pyserial')
    for baud in bauds:
        try:
            ser = serial.Serial(path, baudrate=baud, bytesize=8,
                                parity='N', stopbits=1, timeout=timeout,
                                write_timeout=5)
        except ValueError:
            raise
        except Exception as e:
            raise RuntimeError(f'Cannot open {path}: {e}')
        try:
            ser.reset_input_buffer()
            ser.write(b'\x10\x04\x01')
            ser.flush()
            reply = ser.read(8)
            if len(reply) == 1:
                logger.info(f"Serial printer on {path} answers at {baud}")
                return baud
        except Exception:
            pass
        finally:
            try:
                ser.close()
            except Exception:
                pass
    return None


def _open_network(spec):
    """TCP raw to a network printer (Ethernet/Wi-Fi, usually port 9100).

    Spec: 'socket:HOST' or 'socket:HOST:PORT'. Stdlib only, all platforms.
    """
    import socket
    hostport = spec.split(':', 1)[1]
    host, _, port_s = hostport.partition(':')
    if not host:
        raise ValueError(f'Bad network printer spec: {spec!r}')
    try:
        port = int(port_s or 9100)
    except ValueError:
        raise ValueError(f'Bad network printer spec: {spec!r}')
    try:
        sock = socket.create_connection((host, port), timeout=5)
    except OSError as e:
        raise RuntimeError(f'Cannot reach printer at {host}:{port}: {e}')

    class _SockSink:
        def __init__(self, sock):
            self._sock = sock
            self._fh = sock.makefile('wb')

        def write(self, data):
            self._fh.write(data)

        def flush(self):
            self._fh.flush()

        def close(self):
            try:
                self._fh.close()
            finally:
                try:
                    self._sock.close()
                except OSError:
                    pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self.close()

    return _SockSink(sock)


def _open_win32_raw(name):
    """Windows spooler RAW passthrough (USB printers via their queue).

    Bypasses the driver: ESC/POS bytes go straight to the printer. Needs
    pywin32 (Windows only, imported lazily).
    """
    try:
        import win32print
    except ImportError:
        raise RuntimeError(
            'Windows print queues need pywin32: pip install pywin32')
    if not name:
        raise ValueError('Windows printer name required (win32:<name>)')
    try:
        handle = win32print.OpenPrinter(name)
        win32print.StartDocPrinter(handle, 1, ('POSziona', None, 'RAW'))
        win32print.StartPagePrinter(handle)
    except Exception as e:
        raise RuntimeError(f'Cannot open Windows printer {name!r}: {e}')

    class _WinSink:
        def __init__(self, handle):
            self._handle = handle
            self._closed = False

        def write(self, data):
            import win32print as _wp
            view = memoryview(data)
            while view:
                n = _wp.WritePrinter(self._handle, view.tobytes())
                if not n:
                    raise RuntimeError('Windows spooler refused data')
                view = view[n:]

        def flush(self):
            pass

        def close(self):
            if self._closed:
                return
            self._closed = True
            import win32print as _wp
            try:
                _wp.EndPagePrinter(self._handle)
                _wp.EndDocPrinter(self._handle)
            finally:
                try:
                    _wp.ClosePrinter(self._handle)
                except Exception:
                    pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self.close()

    return _WinSink(handle)


def list_windows_printers():
    """Installed Windows print queues (for picking win32:<name>)."""
    try:
        import win32print
    except ImportError:
        return []
    try:
        flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
        return sorted(p[2] for p in win32print.EnumPrinters(flags) if len(p) > 2 and p[2])
    except Exception:
        return []


def list_windows_com_ports():
    """COM ports present (pyserial, [] when unavailable)."""
    try:
        from serial.tools import list_ports
    except ImportError:
        return []
    try:
        return sorted(p.device for p in list_ports.comports())
    except Exception:
        return []


def _open_device(path, baud):
    """Binary sink for bytes, by path scheme (see module docstring)."""
    import re
    import sys
    if path.startswith('socket:'):
        return _open_network(path)
    if path.startswith('win32:'):
        return _open_win32_raw(path[len('win32:'):].strip())
    if path.startswith('serial:'):
        return _open_serial(path[len('serial:'):].strip(), baud)
    base = os.path.basename(path)
    if base.startswith('tty') or re.fullmatch(r'(?i)com\d+', base):
        return _open_serial(path, baud)
    try:
        return open(path, 'wb')
    except OSError as e:
        hint = ''
        if 'Permission denied' in str(e):
            hint = ' (add the user to the lp/dialout/uucp group?)'
        raise RuntimeError(f'Cannot open {path}: {e.strerror or e}{hint}')


def print_text(db_name, text, cut=None):
    """Print preformatted receipt text on the configured printer.

    Returns {'printed': True, 'device': path}. Raises ValueError on bad
    configuration, RuntimeError when the device fails.
    """
    path, baud, cols, cfg_cut = resolve_device(db_name)
    if cut is None:
        cut = cfg_cut
    if not str(text).strip():
        raise ValueError('Nothing to print')
    data = build_bytes(text, cols=cols, cut=cut)
    try:
        with _open_device(path, baud) as fh:
            fh.write(data)
            fh.flush()
    except (OSError, RuntimeError) as e:
        raise RuntimeError(f'Print failed on {path}: {e}')
    logger.info(f"Printed {len(data)} bytes on {path} (db={db_name})")
    return {'printed': True, 'device': path}
