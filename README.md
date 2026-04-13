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

If you are using Pipenv:

```bash
pipenv run python manage.py migrate
pipenv run python manage.py runserver
```

Open `http://127.0.0.1:8000/` for the landing page, `http://127.0.0.1:8000/queue/` for the queue UI, and `http://127.0.0.1:8000/media/` for the indexed media database.

To populate the database from `/Volumes/media`, run:

```bash
pipenv run python manage.py scan_media
```

## Next steps

- Add models for media files, probes, and remote execution targets.
- Add queue processing for ffmpeg, ffprobe, and mkvpropedit.
- Add authentication before exposing the admin and job controls.
