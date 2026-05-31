#!/usr/bin/env python
import os, random, cgi, sys, datetime
from PIL import Image, ImageFilter
from io import BytesIO

IMAGE_FOLDER = "/srv/http/192.168.1.4/resized/"
LOG_FILE = "log.log"

def crop(img, target_w, target_h):

	w, h = img.size

	left = (w - target_w) // 2
	top = (h - target_h) // 2
	right = left + target_w
	bottom = top + target_h

	return img.crop((left, top, right, bottom))


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

    available_images = get_unlogged_images(LOG_FILE, images)

    if not available_images:
        rollover_log(LOG_FILE)
        available_images = images.copy()

    filename = random.choice(available_images)

    v = cgi.FieldStorage().getvalue('v')
    
    with open(LOG_FILE, 'a') as file:
        dt = datetime.datetime.now().replace(microsecond=0).isoformat().replace('T', ' ')
        file.write(f"{dt} {filename} {v} \n")

    filepath = os.path.join(IMAGE_FOLDER, filename)

    # Load image
    img = Image.open(filepath)
    
    # for portraight pictures crop to a square using width as height
    if img.height > img.width:
        img = crop(img, img.width, img.width)
        
    # Define target size of final image, 4:3, maintain (new) height
    target_h = img.height
    target_w = int(4 * target_h / 3)

    # if image is < 4:3 add blurred sides
    if img.width / img.height < 4 / 3:
   
        # Create blurred background
        bg = img.resize((target_w, target_h), Image.LANCZOS).filter(ImageFilter.GaussianBlur(50))

        # Paste original image centered
        bg.paste(img, ((target_w - img.width) // 2, 0))

        img = bg

    # if images is > 4:3 then crop left and right
    else:

        img = crop(img, target_w, target_h)

    # scale to desired size
    img = img.resize((1600, 1200), Image.LANCZOS)

    buf = BytesIO()
    img.save(buf, format="JPEG", quality=95)
    buf.seek(0)

    sys.stdout.buffer.write(b"Content-Type: image/jpeg\n\n")    
    sys.stdout.flush()

    sys.stdout.buffer.write(buf.read())

except Exception as e:
    print("Content-Type: text/plain\n")
    print(f"Error: {e}")

