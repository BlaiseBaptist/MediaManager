from django import forms

from .models import MediaSource, TranscodeJob


class TranscodeJobForm(forms.ModelForm):
    source_name = forms.CharField(max_length=200, required=False, help_text="Optional display name for a new source.")
    source_path = forms.CharField(max_length=500, help_text="Source path on the local machine or share.")

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
        source_name = self.cleaned_data.get("source_name") or source_path.rsplit("/", 1)[-1] or source_path
        source, _ = MediaSource.objects.get_or_create(
            path=source_path,
            defaults={"name": source_name},
        )
        if source.name != source_name and source_name:
            source.name = source_name
            source.save(update_fields=["name"])
        job.source = source
        if commit:
            job.save()
        return job
