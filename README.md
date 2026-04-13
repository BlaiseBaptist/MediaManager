# MediaManager

Initial Django scaffold for a media queue and transcoding coordinator.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

## Next steps

- Add models for media files, probes, and remote execution targets.
- Add queue processing for ffmpeg, ffprobe, and mkvpropedit.
- Add authentication before exposing the admin and job controls.

