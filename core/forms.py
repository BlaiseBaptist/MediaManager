from django import forms
from pathlib import Path

from .models import MediaFile, MediaSource, TranscodeJob


class TranscodeJobForm(forms.ModelForm):
    source_name = forms.CharField(max_length=200, required=False, help_text="Optional display name for a new source.")
    source_path = forms.CharField(max_length=500, help_text="Source path on the local machine or share.")
    media_path = forms.CharField(max_length=600, help_text="Absolute path to the media file.")

    class Meta:
        model = TranscodeJob
        fields = ["input_path", "command", "priority"]
        widgets = {
            "input_path": forms.TextInput(attrs={"placeholder": "/media/library/movie.mkv"}),
            "command": forms.Textarea(attrs={"rows": 4, "placeholder": "ffmpeg -i ..."}),
        }

    def save(self, commit=True):
        job = super().save(commit=False)
        source_path = self.cleaned_data["source_path"]
        media_path = self.cleaned_data["media_path"]
        source_name = self.cleaned_data.get("source_name") or source_path.rsplit("/", 1)[-1] or source_path
        source_path_obj = Path(source_path)
        media_path_obj = Path(media_path)
        source, _ = MediaSource.objects.get_or_create(
            path=source_path,
            defaults={"name": source_name},
        )
        if source.name != source_name and source_name:
            source.name = source_name
            source.save(update_fields=["name"])
        try:
            relative_path = str(media_path_obj.relative_to(source_path_obj))
        except ValueError:
            relative_path = media_path_obj.name
        media_file, _ = MediaFile.objects.get_or_create(
            absolute_path=media_path,
            defaults={
                "source": source,
                "relative_path": relative_path,
                "file_name": media_path_obj.name,
                "stage": MediaFile.Stage.TRANSCODE_PENDING,
                "is_present": True,
            },
        )
        if media_file.source_id != source.id:
            media_file.source = source
        media_file.relative_path = relative_path
        media_file.file_name = media_path_obj.name
        media_file.stage = MediaFile.Stage.TRANSCODE_PENDING
        media_file.is_present = True
        media_file.save(update_fields=["source", "relative_path", "file_name", "stage", "is_present", "updated_at"])
        job.source = source
        job.media_file = media_file
        job.input_path = media_path
        if commit:
            job.save()
        return job
