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

Worker API:

- `GET /api/worker/jobs/next` claims the next pending transcode job and returns JSON with `id`, `input_url`, and `filename`.
- `GET /api/worker/jobs/<job_id>/input/` streams the file the worker should download.
- Set `MEDIA_MANAGER_AUTH_TOKEN` on the server and client to require a shared bearer token.

To populate the database from `/Volumes/media`, run:

```bash
pipenv run python manage.py scan_media
```

`scan_media` discovers files, runs `ffprobe`, stores container/codec data in `MediaMetadata`, and marks files as either ready or needing processing.

`ffprobe` must be available on the server PATH for metadata extraction to work.

## Next steps

- Add models for media files, probes, and remote execution targets.
- Add queue processing for ffmpeg, ffprobe, and mkvpropedit.
- Add authentication before exposing the admin and job controls.
