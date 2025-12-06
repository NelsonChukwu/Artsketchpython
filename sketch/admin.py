from django.contrib import admin

from .models import Profile, SketchWork


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "display_name", "created_at")


@admin.register(SketchWork)
class SketchWorkAdmin(admin.ModelAdmin):
    list_display = ("user", "created_at")
    list_filter = ("created_at",)
