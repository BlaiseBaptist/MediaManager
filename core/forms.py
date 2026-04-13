import shlex

from django import forms
# from pathlib import Path

from .models import TranscodeProfile


def _split_value_list(value: str) -> list[str]:
    items: list[str] = []
    for raw_line in value.replace(",", "\n").splitlines():
        item = raw_line.strip().lower()
        if item and item not in items:
            items.append(item)
    return items


def _join_value_list(values: list[str]) -> str:
    return "\n".join(str(value).strip() for value in values if str(value).strip())


def _split_ffmpeg_args(value: str) -> list[str]:
    args: list[str] = []
    for raw_line in value.splitlines():
        for token in shlex.split(raw_line):
            if token and token not in args:
                args.append(token)
    return args


class TranscodeProfileForm(forms.ModelForm):
    transcode_ffmpeg_args_text = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 4}),
        label="FFmpeg args",
        help_text="Enter extra ffmpeg args as tokens.",
    )

    class Meta:
        model = TranscodeProfile
        fields = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        profile = self.instance
        if profile and profile.pk:
            self.fields["transcode_ffmpeg_args_text"].initial = _join_value_list(
                profile.transcode_ffmpeg_args
            )

    def save(self, commit=True):
        profile = super().save(commit=False)
        profile.transcode_ffmpeg_args = _split_ffmpeg_args(
            self.cleaned_data["transcode_ffmpeg_args_text"]
        )
        if commit:
            profile.save()
        return profile
