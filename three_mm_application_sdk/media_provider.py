"""Optional image provider. Decoding runs in a resource-bounded child process.

Pillow is optional in the application-host environment; it is never imported by
Core or the file executor. An absent/broken provider leaves ordinary files usable.
"""
import json
import os
import subprocess
import sys
from pathlib import Path


def probe_provider():
    """No image/file input: bounded in-memory provider conformance in a child."""
    roots = dict.fromkeys([str(Path(__file__).parent.parent.resolve()), *(p for p in sys.path if p)])
    environment = {'PATH':os.defpath, 'PYTHONPATH':os.pathsep.join(roots),
        'PYTHONDONTWRITEBYTECODE':'1'}
    try:
        result = subprocess.run([sys.executable, '-c',
            'from three_mm_application_sdk.media_provider import probe_worker; probe_worker()'],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            env=environment, close_fds=True, timeout=2)
        return 'ready' if result.returncode == 0 else 'unavailable' if result.returncode == 3 else 'unknown'
    except (OSError, subprocess.TimeoutExpired): return 'unknown'


def probe_worker():
    import resource
    resource.setrlimit(resource.RLIMIT_CPU, (3, 3))
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    try:
        from PIL import Image
    except ImportError: sys.exit(3)
    try:
        import io
        for format in ('PNG', 'JPEG', 'WEBP'):
            output = io.BytesIO(); Image.new('RGB', (1,1)).save(output, format=format)
            Image.open(io.BytesIO(output.getvalue())).load()
    except Exception: sys.exit(4)


def transform_image(source_fd, output_fd, parameters, max_bytes):
    environment = {'PATH': os.defpath, 'PYTHONPATH': os.pathsep.join(p for p in sys.path if p)}
    process = subprocess.Popen(
        [sys.executable, '-c', 'from three_mm_application_sdk.media_provider import worker; worker()',
         str(source_fd), str(output_fd), json.dumps({k: parameters[k] for k in ('width', 'height', 'format')}), str(max_bytes)],
        pass_fds=(source_fd, output_fd), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, env=environment, close_fds=True,
    )
    try:
        code = process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2)
        raise RuntimeError('transform_failed') from None
    if code:
        raise RuntimeError('provider_unavailable' if code == 3 else 'transform_failed')


def worker():
    import resource
    source, output = int(sys.argv[1]), int(sys.argv[2])
    parameters, max_bytes = json.loads(sys.argv[3]), int(sys.argv[4])
    resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_FSIZE, (max_bytes, max_bytes))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    try:
        from PIL import Image, ImageOps, UnidentifiedImageError
    except ImportError:
        sys.exit(3)
    import warnings
    warnings.simplefilter('error', Image.DecompressionBombWarning)
    Image.MAX_IMAGE_PIXELS = 16 * 1024 * 1024
    try:
        with os.fdopen(source, 'rb') as stream, Image.open(stream) as image:
            if image.format not in {'PNG', 'JPEG', 'WEBP'} or image.width * image.height > Image.MAX_IMAGE_PIXELS or getattr(image, 'n_frames', 1) != 1:
                raise ValueError('Unsupported image')
            image.load()
            image = ImageOps.exif_transpose(image)
            image.thumbnail((parameters['width'], parameters['height']))
            # A fresh pixel-only image strips EXIF/ICC/comments and other source
            # metadata. Never serve the user-supplied active content as inline.
            mode = 'RGB' if parameters['format'] == 'jpeg' else 'RGBA'
            clean = Image.new(mode, image.size)
            clean.paste(image.convert(mode))
            with os.fdopen(output, 'wb') as target:
                clean.save(target, format=parameters['format'].upper())
                target.flush()
                os.fsync(target.fileno())
    except Exception:
        sys.exit(4)
