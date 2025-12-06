from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User


class UploadForm(forms.Form):
    image = forms.ImageField(label="Upload an image to sketch")
    sketch_style = forms.ChoiceField(
        choices=[("artistic", "Artistic pencil work"), ("clean", "Clean technical lines"), ("trace", "Trace/outline")],
        initial="artistic",
        label="Sketch style",
    )
    sketch_depth = forms.ChoiceField(
        choices=[
            ("none", "No depth"),
            ("light", "Light depth"),
            ("medium", "Balanced depth"),
            ("deep", "Rich depth"),
        ],
        initial="medium",
        label="Sketch depth",
    )
    output_size = forms.ChoiceField(
        choices=[
            ("orig", "Original dimensions"),
            ("lg", "Large (max 1600px)"),
            ("md", "Medium (max 1024px)"),
            ("sm", "Small (max 720px)"),
            ("xs", "Compact (max 480px)"),
        ],
        initial="orig",
        label="Output size",
    )


class SignUpForm(UserCreationForm):
    email = forms.EmailField(required=True)
    first_name = forms.CharField(max_length=30, required=False)
    last_name = forms.CharField(max_length=30, required=False)

    class Meta:
        model = User
        fields = ("username", "email", "first_name", "last_name", "password1", "password2")
