from django.conf import settings
from django.db import models
from django.utils import timezone


class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    display_name = models.CharField(max_length=150, blank=True)
    bio = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return self.display_name or self.user.get_username()


def upload_path(instance, filename):
    return f"user_uploads/{instance.user_id}/{timezone.now().strftime('%Y%m%d%H%M%S')}_{filename}"


def sketch_path(instance, filename):
    return f"user_sketches/{instance.user_id}/{timezone.now().strftime('%Y%m%d%H%M%S')}_{filename}"


class SketchWork(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sketches")
    original_image = models.ImageField(upload_to=upload_path, blank=True, null=True)  # kept optional; only sketches persisted
    sketch_image = models.ImageField(upload_to=sketch_path)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"Sketch by {self.user.get_username()} on {self.created_at:%Y-%m-%d}"
