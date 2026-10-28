#!/usr/bin/env python
import os, random, cgi, sys, datetime
from PIL import Image, ImageFilter, ImageDraw, ImageChops
from io import BytesIO

IMAGE_FOLDER = "/srv/http/192.168.1.4/resized/"
LOG_FILE = "log.log"
BLUR_RADIUS = 50        # blur strength of mirrored side fill
DATE_STAMP = True       # stamp EXIF date taken, bottom right, in old film camera style
STAMP_CORE = (255, 150, 40)     # glowing orange LED digits
STAMP_GLOW = (255, 60, 0)       # red-orange halo around the digits

def crop(img, target_w, target_h):

	w, h = img.size

	left = (w - target_w) // 2
	top = (h - target_h) // 2
	right = left + target_w
	bottom = top + target_h

	return img.crop((left, top, right, bottom))


def mirror_fill(img, target_w, target_h):
    # Extend image to target width by mirroring each edge outward and blurring the extension
    img = img.convert("RGB")
    w = img.width
    pad_l = (target_w - w) // 2
    pad_r = target_w - w - pad_l

    canvas = Image.new("RGB", (target_w, target_h))
    canvas.paste(img, (pad_l, 0))
    if pad_l > 0:
        canvas.paste(img.crop((0, 0, pad_l, target_h)).transpose(Image.FLIP_LEFT_RIGHT), (0, 0))
    if pad_r > 0:
        canvas.paste(img.crop((w - pad_r, 0, w, target_h)).transpose(Image.FLIP_LEFT_RIGHT), (pad_l + w, 0))

    # Blur everything, then paste the sharp original back over the centre
    canvas = canvas.filter(ImageFilter.GaussianBlur(BLUR_RADIUS))
    canvas.paste(img, (pad_l, 0))

    return canvas

# Seven segment layout: a=top b=top right c=bottom right d=bottom e=bottom left f=top left g=middle
SEGMENTS = {
    "0": "abcdef", "1": "bc", "2": "abged", "3": "abgcd", "4": "fgbc",
    "5": "afgcd", "6": "afgedc", "7": "abc", "8": "abcdefg", "9": "abcdfg",
}


def exif_date(img):
    # Date taken from EXIF as (year, month, day), or None if missing/invalid
    try:
        exif = img.getexif()
        sub = exif.get_ifd(0x8769)
        raw = sub.get(0x9003) or sub.get(0x9004) or exif.get(0x0132)
        d = datetime.datetime.strptime(str(raw).strip()[:10], "%Y:%m:%d")
        return d.year, d.month, d.day
    except Exception:
        return None


def draw_stamp_text(draw, text, x, y, h, colour):
    # Draw text as slanted seven segment digits, top-left at (x, y), digit height h
    w = h * 0.55            # digit width
    t = h * 0.13            # segment thickness
    gap = h * 0.30
    slant = 0.12

    def pt(px, py):
        return (px + (y + h - py) * slant, py)

    def seg(x0, y0, x1, y1):
        # hexagonal segment between two end points along an axis
        if y0 == y1:
            pts = [(x0, y0), (x0 + t / 2, y0 - t / 2), (x1 - t / 2, y0 - t / 2),
                   (x1, y0), (x1 - t / 2, y0 + t / 2), (x0 + t / 2, y0 + t / 2)]
        else:
            pts = [(x0, y0), (x0 + t / 2, y0 + t / 2), (x0 + t / 2, y1 - t / 2),
                   (x0, y1), (x0 - t / 2, y1 - t / 2), (x0 - t / 2, y0 + t / 2)]
        draw.polygon([pt(*p) for p in pts], fill=colour)

    for ch in text:
        if ch == " ":
            x += w
        elif ch == "'":
            # film cameras show the year as '98
            draw.polygon([pt(x + t * 0.2, y), pt(x + t * 1.4, y), pt(x + t * 0.6, y + h * 0.3),
                          pt(x - t * 0.4, y + h * 0.3)], fill=colour)
            x += t * 1.4 + gap
        else:
            xl, xr, ym = x + t / 2, x + w - t / 2, y + h / 2
            yt, yb = y + t / 2, y + h - t / 2
            i = t * 0.15    # small gap so segments don't touch
            lines = {"a": (xl + i, yt, xr - i, yt), "g": (xl + i, ym, xr - i, ym),
                     "d": (xl + i, yb, xr - i, yb), "f": (xl, yt + i, xl, ym - i),
                     "e": (xl, ym + i, xl, yb - i), "b": (xr, yt + i, xr, ym - i),
                     "c": (xr, ym + i, xr, yb - i)}
            for s in SEGMENTS[ch]:
                seg(*lines[s])
            x += w + gap


def add_date_stamp(img, date):
    # Orange film camera style date, bottom right: '98 10 28
    img = img.convert("RGB")
    text = "'%02d %02d %02d" % (date[0] % 100, date[1], date[2])
    h = img.height * 0.045
    margin = img.height * 0.05
    # measure with a dummy draw, then right-align
    class Meter:
        right = 0
        def polygon(self, pts, fill=None):
            self.right = max(self.right, max(p[0] for p in pts))
    m = Meter()
    draw_stamp_text(m, text, 0, 0, h, None)
    x = img.width - margin - m.right
    y = img.height - margin - h

    glow = Image.new("RGB", img.size, (0, 0, 0))
    draw_stamp_text(ImageDraw.Draw(glow), text, x, y, h, STAMP_GLOW)
    glow = glow.filter(ImageFilter.GaussianBlur(h * 0.12))
    core = Image.new("RGB", img.size, (0, 0, 0))
    draw_stamp_text(ImageDraw.Draw(core), text, x, y, h, STAMP_CORE)

    # screen blend: light only, like exposed film
    img = ImageChops.screen(img, glow)
    img = ImageChops.screen(img, core)
    return img


def get_unlogged_images(log_path, image_names):
    available = set(image_names)

    if not available:
        return []

    if not os.path.exists(log_path):
        return image_names.copy()

    try:
        with open(log_path, 'r', encoding='utf-8', errors='ignore') as log_file:
            for line in log_file:
                if not available:
                    break
                stripped = line.strip()
                if not stripped:
                    continue
                # Expected format: DATE TIME FILE NAME WITH SPACES VOLTAGE
                # Split from the right to peel off voltage, then isolate filename.
                left_and_name = stripped.rsplit(" ", 1)
                if len(left_and_name) != 2:
                    continue
                date_time_and_name = left_and_name[0].split(" ", 2)
                if len(date_time_and_name) != 3:
                    continue
                image_name = date_time_and_name[2]
                if image_name in available:
                    available.remove(image_name)
    except OSError:
        return [img for img in image_names if img in available]

    # Preserve original directory listing order for reproducibility.
    return [img for img in image_names if img in available]


def rollover_log(log_path):
    if not os.path.exists(log_path):
        return

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_path = f"{log_path}.{timestamp}"

    try:
        os.replace(log_path, archive_path)
    except OSError:
        # Fallback to truncating if archiving fails.
        try:
            with open(log_path, 'w', encoding='utf-8'):
                pass
        except OSError:
            pass


try:
    images = [f for f in os.listdir(IMAGE_FOLDER)
        if f.lower().endswith((".jpg", ".jpeg", ".png"))]

    if not images:
        print("Content-Type: text/plain\n")
        print("No images found")
        sys.exit(0)

    form = cgi.FieldStorage()
    requested = form.getvalue('image')

    # specific image requested: skip the log entirely
    if requested:
        filename = os.path.basename(requested)
        if filename not in images:
            print("Content-Type: text/plain\n")
            print(f"Image not found: {filename}")
            sys.exit(0)

    else:
        available_images = get_unlogged_images(LOG_FILE, images)

        if not available_images:
            rollover_log(LOG_FILE)
            available_images = images.copy()

        filename = random.choice(available_images)

        voltage = form.getvalue('v')

        # only log when a voltage is supplied (e.g. skip manual/test requests)
        if voltage:
            with open(LOG_FILE, 'a') as file:
                dt = datetime.datetime.now().replace(microsecond=0).isoformat().replace('T', ' ')
                file.write(f"{dt} {filename} {voltage} \n")

    filepath = os.path.join(IMAGE_FOLDER, filename)

    # Load image
    img = Image.open(filepath)
    stamp_date = exif_date(img) if DATE_STAMP else None
    
    # for portraight pictures crop to a square using width as height
    if img.height > img.width:
        img = crop(img, img.width, img.width)
        
    # Define target size of final image, 4:3, maintain (new) height
    target_h = img.height
    target_w = int(4 * target_h / 3)

    # if image is < 4:3 add mirrored, blurred sides
    if img.width / img.height < 4 / 3:

        img = mirror_fill(img, target_w, target_h)

    # if images is > 4:3 then crop left and right
    else:

        img = crop(img, target_w, target_h)

    # scale to desired size
    img = img.resize((1600, 1200), Image.LANCZOS)

    if stamp_date:
        img = add_date_stamp(img, stamp_date)

    buf = BytesIO()
    img.save(buf, format="JPEG", quality=95)
    buf.seek(0)

    sys.stdout.buffer.write(b"Content-Type: image/jpeg\n\n")    
    sys.stdout.flush()

    sys.stdout.buffer.write(buf.read())

except Exception as e:
    print("Content-Type: text/plain\n")
    print(f"Error: {e}")

