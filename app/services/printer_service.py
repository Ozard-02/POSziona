"""
Thermal receipt printing for Posziona (ESC/POS, stdlib only).

Design: the POS already builds receipt *text* in the browser
(`buildReceipt` in pos.js, incl. kitchen slips). The server only
converts that text to ESC/POS bytes and pushes them to the device —
no receipt-layout duplication, no new dependencies (matters for the
frozen binary: python-escpos/pyusb would need system libusb too).

Transports (all plain byte sinks):
- /dev/usb/lp*  — USB printers claimed by the usblp kernel driver.
- /dev/ttyUSB* / /dev/ttyS* — serial printers / USB-serial adapters
  (baud set via termios, Linux only).
- 'auto' — first existing of the above (USB preferred).
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
    No codepage / font commands: works on any default configuration.
    """
    body = []
    for raw_line in str(text).split('\n'):
        for part in sanitize_line(raw_line, cols).split('\n'):
            body.append(part.encode('ascii') + b'\n')
    data = bytearray()
    data += ESC + b'@'          # init
    data += ESC + b'a\x00'      # left align
    data += b''.join(body)
    data += ESC + b'd\x04'      # feed 4 lines
    if cut:
        data += GS + b'V\x01'   # partial cut
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
    raw_path = (settings.get('printer_path') or '').strip()
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
        for pattern in ('/dev/usb/lp*', '/dev/ttyUSB*'):
            candidates = sorted(glob.glob(pattern))
            if candidates:
                return candidates[0], baud, cols, cut
        raise ValueError('No printer found (probed /dev/usb/lp*, /dev/ttyUSB*)')
    return raw_path, baud, cols, cut


def _open_serial(path, baud):
    """Open a serial device at baud, 8N1 raw (Linux only)."""
    try:
        import termios
    except ImportError:
        raise RuntimeError('Serial printers need Linux (termios unavailable)')
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


DETECT_BAUDS = (9600, 19200, 38400, 57600, 115200)


def detect_serial(path, bauds=DETECT_BAUDS, timeout=0.6):
    """Find the baud rate of an ESC/POS serial printer, or None.

    Sends DLE EOT (real-time status request) at each baud and waits for
    the 1-byte reply. Open/config failures raise immediately (wrong
    permissions etc. won't heal at another baud); silence tries the next.
    """
    import select
    for baud in bauds:
        try:
            fh = _open_serial(path, baud)
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


def _open_device(path, baud):
    """Binary sink for bytes: serial (termios) or plain file write."""
    if os.path.basename(path).startswith('tty'):
        return _open_serial(path, baud)
    try:
        return open(path, 'wb')
    except OSError as e:
        hint = ''
        if 'Permission denied' in str(e):
            hint = ' (add the user to the lp/dialout group?)'
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
