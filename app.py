from flask import Flask, render_template, request, send_file, jsonify
from PIL import Image, ImageOps
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, A5, LETTER, legal
from reportlab.lib.utils import ImageReader
from werkzeug.utils import secure_filename
from io import BytesIO
import os

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 40 * 1024 * 1024  # 40 MB total request
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
PAGE_SIZES = {"A4": A4, "A5": A5, "Letter": LETTER, "Legal": legal}

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def parse_float(value, default, minimum, maximum):
    try:
        return max(minimum, min(maximum, float(value)))
    except (TypeError, ValueError):
        return default

@app.get("/")
def index():
    return render_template("index.html")

@app.post("/convert")
def convert():
    uploads = request.files.getlist("images")
    if not uploads or not any(f.filename for f in uploads):
        return jsonify(error="Please add at least one image."), 400

    page_choice = request.form.get("page_size", "A4")
    orientation = request.form.get("orientation", "portrait")
    fit_mode = request.form.get("fit_mode", "fit")
    margin_mm = parse_float(request.form.get("margin", "10"), 10, 0, 40)
    quality = request.form.get("quality", "high")

    page_w, page_h = PAGE_SIZES.get(page_choice, A4)
    if orientation == "landscape":
        page_w, page_h = max(page_w, page_h), min(page_w, page_h)
    else:
        page_w, page_h = min(page_w, page_h), max(page_w, page_h)

    margin = margin_mm * 72 / 25.4
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(page_w, page_h), pageCompression=1)
    image_count = 0

    for uploaded in uploads:
        if not uploaded.filename:
            continue
        if not allowed_file(uploaded.filename):
            return jsonify(error=f"Unsupported file type: {secure_filename(uploaded.filename)}"), 400
        try:
            image = Image.open(uploaded.stream)
            image = ImageOps.exif_transpose(image)
            if image.mode not in ("RGB", "L"):
                if "A" in image.getbands():
                    background = Image.new("RGB", image.size, "white")
                    alpha = image.getchannel("A")
                    background.paste(image.convert("RGB"), mask=alpha)
                    image = background
                else:
                    image = image.convert("RGB")
            elif image.mode == "L":
                image = image.convert("RGB")
            image.load()
        except Exception:
            return jsonify(error=f"Could not read image: {secure_filename(uploaded.filename)}"), 400

        iw, ih = image.size
        available_w = max(1, page_w - 2 * margin)
        available_h = max(1, page_h - 2 * margin)
        scale = min(available_w / iw, available_h / ih)
        if fit_mode == "fill":
            scale = max(available_w / iw, available_h / ih)
        draw_w, draw_h = iw * scale, ih * scale
        x = (page_w - draw_w) / 2
        y = (page_h - draw_h) / 2

        image_buffer = BytesIO()
        save_quality = 92 if quality == "high" else 78 if quality == "medium" else 60
        image.save(image_buffer, format="JPEG", quality=save_quality, optimize=True)
        image_buffer.seek(0)
        pdf.drawImage(ImageReader(image_buffer), x, y, width=draw_w, height=draw_h,
                      preserveAspectRatio=True, mask="auto")
        pdf.showPage()
        image_count += 1

    if image_count == 0:
        return jsonify(error="No valid images were found."), 400

    pdf.save()
    buffer.seek(0)
    return send_file(buffer, mimetype="application/pdf", as_attachment=True,
                     download_name="converted-images.pdf")

@app.errorhandler(413)
def too_large(_error):
    return jsonify(error="The selected files are too large. Please keep the total under 40 MB."), 413

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
