from django import forms
from pathlib import Path

from .models import MediaFile, MediaSource, TranscodeJob, TranscodeProfile


def _split_value_list(value: str) -> list[str]:
    items: list[str] = []
    for raw_line in value.replace(",", "\n").splitlines():
        item = raw_line.strip().lower()
        if item and item not in items:
            items.append(item)
    return items


def _join_value_list(values: list[str]) -> str:
    return "\n".join(str(value).strip() for value in values if str(value).strip())


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


class TranscodeProfileForm(forms.ModelForm):
    target_video_codecs_text = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        label="Target video codecs",
        help_text="Enter one codec per line, or separate with commas.",
    )
    target_audio_codecs_text = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        label="Target audio codecs",
        help_text="Enter one codec per line, or separate with commas.",
    )
    target_subtitle_codecs_text = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        label="Target subtitle codecs",
        help_text="Enter one codec per line, or separate with commas.",
    )
    transcode_ffmpeg_args_text = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 4}),
        label="FFmpeg args",
        help_text="Enter one ffmpeg argument per line, in the order they should be appended.",
    )

    class Meta:
        model = TranscodeProfile
        fields = [
            "target_container_contains",
            "transcode_quality",
            "transcode_video_codec",
            "transcode_audio_codec",
            "output_extension",
        ]
        widgets = {
            "target_container_contains": forms.TextInput(attrs={"placeholder": "matroska"}),
            "transcode_quality": forms.TextInput(attrs={"placeholder": "23"}),
            "transcode_video_codec": forms.TextInput(attrs={"placeholder": "libx264"}),
            "transcode_audio_codec": forms.TextInput(attrs={"placeholder": "aac"}),
            "output_extension": forms.TextInput(attrs={"placeholder": ".mp4"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        profile = self.instance
        if profile and profile.pk:
            self.fields["target_video_codecs_text"].initial = _join_value_list(profile.target_video_codecs)
            self.fields["target_audio_codecs_text"].initial = _join_value_list(profile.target_audio_codecs)
            self.fields["target_subtitle_codecs_text"].initial = _join_value_list(profile.target_subtitle_codecs)
            self.fields["transcode_ffmpeg_args_text"].initial = _join_value_list(profile.transcode_ffmpeg_args)

    def clean(self):
        cleaned_data = super().clean()
        cleaned_data["target_video_codecs"] = _split_value_list(cleaned_data.get("target_video_codecs_text", ""))
        cleaned_data["target_audio_codecs"] = _split_value_list(cleaned_data.get("target_audio_codecs_text", ""))
        cleaned_data["target_subtitle_codecs"] = _split_value_list(cleaned_data.get("target_subtitle_codecs_text", ""))
        cleaned_data["transcode_ffmpeg_args"] = [
            value for value in (line.strip() for line in cleaned_data.get("transcode_ffmpeg_args_text", "").splitlines()) if value
        ]
        return cleaned_data

    def save(self, commit=True):
        profile = super().save(commit=False)
        profile.target_video_codecs = self.cleaned_data["target_video_codecs"]
        profile.target_audio_codecs = self.cleaned_data["target_audio_codecs"]
        profile.target_subtitle_codecs = self.cleaned_data["target_subtitle_codecs"]
        profile.transcode_ffmpeg_args = self.cleaned_data["transcode_ffmpeg_args"]
        if commit:
            profile.save()
        return profile
