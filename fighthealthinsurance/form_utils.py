from django import forms
from django.core.exceptions import ValidationError


# See https://docs.djangoproject.com/en/5.1/topics/http/file-uploads/
class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


ALLOWED_EXTENSIONS = ["pdf", "jpg", "jpeg", "png", "docx"]
MAX_FILE_SIZE = 5 * 1024 * 1024
TOTAL_UPLOAD_SIZE_LIMIT = 20 * 1024 * 1024


class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        validated_files = []
        total_size = 0  # Track total size of uploaded files

        if isinstance(data, (list, tuple)):
            for file in data:
                validated_file = self.validate_file(single_file_clean(file, initial))
                validated_files.append(validated_file)
                total_size += validated_file.size
        else:
            validated_file = self.validate_file(single_file_clean(data, initial))
            validated_files.append(validated_file)
            total_size += validated_file.size

        # Enforce total upload size limit
        if total_size > TOTAL_UPLOAD_SIZE_LIMIT:
            raise ValidationError(
                f"Total upload size exceeds {TOTAL_UPLOAD_SIZE_LIMIT / (1024 * 1024)}MB. "
                "Please reduce the number or size of files."
            )

        return validated_files

    def validate_file(self, file):
        if not file:
            return None

        # Validate file extension
        ext = file.name.split(".")[-1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise ValidationError(f"Invalid file extension: .{ext}. Allowed: {', '.join(ALLOWED_EXTENSIONS)}")

        # Validate individual file size
        if file.size > MAX_FILE_SIZE:
            raise ValidationError(f"File size exceeds the limit of {MAX_FILE_SIZE / (1024 * 1024)}MB.")

        return file
