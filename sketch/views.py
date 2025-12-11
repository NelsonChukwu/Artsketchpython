import io
from datetime import datetime
from uuid import uuid4

import numpy as np
from django.core.files.base import ContentFile
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect, render
from PIL import Image, ImageFilter, ImageOps

from .forms import SignUpForm, UploadForm
from .models import SketchWork


def _pencil_sketch(image_file, sketch_style="artistic", sketch_depth="medium", output_size="orig"):
    """Convert an image file-like object to a pencil sketch PIL image."""
    image = Image.open(image_file).convert("RGB")
    image.thumbnail((1800, 1800))

    # Base grayscale with preserved midtones
    gray = ImageOps.grayscale(image)
    gray = ImageOps.autocontrast(gray, cutoff=1)

    # Dodge blend to lift highlights while keeping structure
    inverted = ImageOps.invert(gray)
    blurred = inverted.filter(ImageFilter.GaussianBlur(radius=22))
    gray_arr = np.asarray(gray, dtype=np.float32)
    blur_arr = np.asarray(blurred, dtype=np.float32)
    dodge = np.clip(gray_arr * 255.0 / (255.0 - blur_arr + 1e-4), 0, 255)

    # Gentle sharpening to bring back contours
    dodge_img = Image.fromarray(dodge.astype(np.uint8))
    sharp = dodge_img.filter(ImageFilter.UnsharpMask(radius=2, percent=180, threshold=2))

    # Paper grain simulation blended in to mimic pencil texture
    w, h = sharp.size
    texture = np.random.normal(loc=128, scale=18, size=(h, w)).astype(np.float32)
    texture = Image.fromarray(np.clip(texture, 0, 255).astype(np.uint8))
    texture = texture.filter(ImageFilter.GaussianBlur(radius=1.4))
    texture_arr = np.asarray(texture, dtype=np.float32)
    sharp_arr = np.asarray(sharp, dtype=np.float32)

    blended = np.clip(0.85 * sharp_arr + 0.15 * texture_arr, 0, 255)
    base_sketch = Image.fromarray(blended.astype(np.uint8)).convert("RGB")

    # Style tuning: artistic mixes texture, clean favors tidy lines, trace keeps faint outlines
    luminance = base_sketch.convert("L")
    if sketch_style == "trace":
        # Denoise before edge detection to avoid paper grain noise
        base = gray.filter(ImageFilter.MedianFilter(size=3)).filter(ImageFilter.GaussianBlur(radius=1.6))
        edges = base.filter(ImageFilter.FIND_EDGES)
        edges = ImageOps.autocontrast(edges, cutoff=1)
        edges_arr = np.asarray(edges, dtype=np.float32)

        # Keep only strongest edges to avoid interior shading noise
        threshold = np.percentile(edges_arr, 92.0)
        mask = edges_arr >= threshold
        lines = np.full_like(edges_arr, 255.0)
        lines[mask] = 60.0

        line_img = Image.fromarray(lines.astype(np.uint8))
        line_img = line_img.filter(ImageFilter.MaxFilter(size=3))  # thicken outlines slightly
        sketch = line_img.convert("RGB")
        sketch_depth = "none"
    elif sketch_style == "artistic":
        strokes = gray.filter(ImageFilter.FIND_EDGES)
        strokes = ImageOps.autocontrast(strokes, cutoff=2)
        strokes = strokes.filter(ImageFilter.UnsharpMask(radius=1.2, percent=250, threshold=1))
        strokes_arr = np.asarray(strokes, dtype=np.float32)
        lumi_arr = np.asarray(luminance, dtype=np.float32)
        mixed = np.clip(0.65 * lumi_arr + 0.35 * strokes_arr, 0, 255)
        sketch = Image.fromarray(mixed.astype(np.uint8))
        sketch = sketch.filter(ImageFilter.UnsharpMask(radius=1.5, percent=160, threshold=2)).convert("RGB")
    else:
        clean = ImageOps.autocontrast(luminance, cutoff=0.5)
        clean = clean.filter(ImageFilter.UnsharpMask(radius=1.1, percent=140, threshold=2))
        sketch = clean.convert("RGB")

    # Controlled sketch depth (tonal lift)
    shade_strength = {"none": 0.0, "light": 0.22, "medium": 0.38, "deep": 0.55}.get(sketch_depth, 0.38)
    if shade_strength > 0:
        tone = gray.filter(ImageFilter.GaussianBlur(radius=3.2))
        tone = ImageOps.autocontrast(tone, cutoff=2)
        tone_arr = np.asarray(tone, dtype=np.float32)
        sketch_arr = np.asarray(sketch.convert("L"), dtype=np.float32)
        shaded = np.clip((1 - 0.35 * shade_strength) * sketch_arr + shade_strength * tone_arr, 0, 255)
        shaded_img = Image.fromarray(shaded.astype(np.uint8))
        shaded_img = ImageOps.autocontrast(shaded_img, cutoff=1)
        sketch = shaded_img.convert("RGB")

    # Optional resizing
    size_map = {"orig": None, "lg": 1600, "md": 1024, "sm": 720, "xs": 480}
    target_max = size_map.get(output_size, None)
    if target_max:
        sketch.thumbnail((target_max, target_max))

    return sketch


def landing(request):
    return render(request, "landing.html")


def signup(request):
    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Welcome! Your account is ready.")
            return redirect("dashboard")
    else:
        form = SignUpForm()
    return render(request, "registration/signup.html", {"form": form})


def logout_view(request):
    logout(request)
    return redirect("landing")


@login_required
def dashboard(request):
    tab = request.GET.get("tab", "upload")
    form = UploadForm()
    result_url = None

    if request.method == "POST":
        form = UploadForm(request.POST, request.FILES)
        if form.is_valid():
            upload = form.cleaned_data["image"]
            upload_content = upload.read()

            work = SketchWork(user=request.user)

            sketch_image = _pencil_sketch(
                io.BytesIO(upload_content),
                sketch_style=form.cleaned_data["sketch_style"],
                sketch_depth=form.cleaned_data["sketch_depth"],
                output_size=form.cleaned_data["output_size"],
            )
            buffer = io.BytesIO()
            sketch_image.save(buffer, format="PNG", optimize=True)
            buffer.seek(0)
            work.sketch_image.save(f"sketch_{uuid4().hex}.png", ContentFile(buffer.getvalue()), save=False)
            work.save()

            result_url = work.sketch_image.url
            messages.success(request, "Sketch generated successfully.")
            tab = "upload"
        else:
            messages.error(request, "Please upload a valid image file.")

    recent_qs = SketchWork.objects.filter(user=request.user).order_by("-created_at")
    q = request.GET.get("q", "").strip()
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")

    if q:
        recent_qs = recent_qs.filter(sketch_image__icontains=q)
    if start_date:
        try:
            dt = datetime.fromisoformat(start_date)
            recent_qs = recent_qs.filter(created_at__date__gte=dt.date())
        except ValueError:
            pass
    if end_date:
        try:
            dt = datetime.fromisoformat(end_date)
            recent_qs = recent_qs.filter(created_at__date__lte=dt.date())
        except ValueError:
            pass

    recent = list(recent_qs[:30])

    return render(
        request,
        "sketch/dashboard.html",
        {
            "form": form,
            "result_url": result_url,
            "recent": recent,
            "tab": tab,
            "filters": {"q": q, "start_date": start_date or "", "end_date": end_date or "", "size": request.GET.get("size", "orig")},
        },
    )


def section(request, slug):
    sections = {
        "create": {
            "title": "Create",
            "lead": "Bring images in, jumpstart sketches, or explore ready-made templates.",
            "items": [
                "Import Artwork / Capture Photo",
                "Procedural Sketch Generator",
                "Template Gallery",
            ],
        },
        "editor": {
            "title": "Editor",
            "lead": "Full-featured canvas with layers, brushes, masks, and precise transforms.",
            "items": [
                "Canvas Workspace",
                "Layers",
                "Brushes & Tools",
                "Masks & Local Editing",
                "Transform Tools",
            ],
        },
        "ai-enhancement": {
            "title": "AI Enhancement",
            "lead": "Enhance, stylize, refine, and upscale your sketches with AI tooling.",
            "items": [
                "Enhance Artwork (Image-to-Image)",
                "Shading & Detail Refinement",
                "AI Illusion Generation",
                "Style Transfer",
                "Super-Resolution Upscaling",
                "Colorization",
            ],
        },
        "projects": {
            "title": "Projects",
            "lead": "Stay organized with versions, autosaves, and shared collaborations.",
            "items": ["My Projects", "Version History", "Autosaved Drafts", "Shared Collaborations"],
        },
        "community": {
            "title": "Gallery",
            "lead": "Share illusions and AR-ready pieces—upload progress or finished work as photos or videos.",
            "items": [
                "Progress work (photo or video uploads)",
                "Finished work (photo or video uploads)",
                "Illusion showcase",
                "Augmented Reality (AR) experiences",
            ],
        },
        "account": {
            "title": "Account",
            "lead": "Manage your profile, presets, preferences, billing, and sessions.",
            "items": ["My Profile", "Saved Styles / Presets", "Settings", "Billing / Credits", "Sign Out"],
        },
    }
    section_data = sections.get(slug)
    if not section_data:
        section_data = {"title": "Hybrid Artistic Engine", "lead": "Discover what you can create.", "items": []}
    return render(request, "sketch/section.html", {"section": section_data})


@login_required
def download_all(request):
    # Apply same filters for consistency
    recent_qs = SketchWork.objects.filter(user=request.user).order_by("-created_at")
    q = request.GET.get("q", "").strip()
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")

    if q:
        recent_qs = recent_qs.filter(sketch_image__icontains=q)
    if start_date:
        try:
            dt = datetime.fromisoformat(start_date)
            recent_qs = recent_qs.filter(created_at__date__gte=dt.date())
        except ValueError:
            pass
    if end_date:
        try:
            dt = datetime.fromisoformat(end_date)
            recent_qs = recent_qs.filter(created_at__date__lte=dt.date())
        except ValueError:
            pass

    buffer = io.BytesIO()
    import zipfile

    # Handle optional dimension scaling
    size_code = request.GET.get("size", "orig")
    size_map = {
        "orig": None,
        "lg": 1600,
        "md": 1024,
        "sm": 720,
        "xs": 480,
    }
    target_max = size_map.get(size_code, None)

    def _resize_if_needed(image_file, filename):
        if not target_max:
            return filename, image_file.read()
        with Image.open(image_file) as img:
            img = img.convert("RGB")
            img.thumbnail((target_max, target_max))
            buffer_inner = io.BytesIO()
            img.save(buffer_inner, format="PNG", optimize=True)
            buffer_inner.seek(0)
            name_parts = filename.rsplit(".", 1)
            sized_name = f"{name_parts[0]}_{size_code}.png"
            return sized_name, buffer_inner.getvalue()

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for work in recent_qs:
            filename = work.sketch_image.name.split("/")[-1]
            with work.sketch_image.open("rb") as fh:
                out_name, out_bytes = _resize_if_needed(fh, filename)
                zf.writestr(out_name, out_bytes)
    buffer.seek(0)
    response = HttpResponse(buffer.getvalue(), content_type="application/zip")
    response["Content-Disposition"] = 'attachment; filename="sketches.zip"'
    return response
