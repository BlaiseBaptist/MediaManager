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

To publish the site over Tailscale Serve, set the external hostname and trusted origin, then proxy your local Django port:

```bash
export MEDIA_MANAGER_ALLOWED_HOSTS=your-node.your-tailnet.ts.net
export MEDIA_MANAGER_CSRF_TRUSTED_ORIGINS=https://your-node.your-tailnet.ts.net
python manage.py runserver 127.0.0.1:8000
tailscale serve --bg localhost:8000
```

`tailscale serve` requires HTTPS to be enabled in your tailnet. The worker API will emit HTTPS URLs when Django sees the forwarded proxy headers.

If serving large files through Django is too slow, point the worker at the existing lighttpd file server instead:

```bash
export MEDIA_MANAGER_FILE_BASE_URL=https://your-node.your-tailnet.ts.net/
```

With that set, job payloads will hand workers a direct file URL from lighttpd instead of proxying the bytes through Django. Use the actual base URL that serves `/media`.

The worker now defaults to HTTP/2-capable requests. If you need HTTP/1 for a particular proxy, set `MEDIA_MANAGER_FORCE_HTTP1=1`.

Worker API:

- `GET /api/worker/jobs/next?worker_id=<worker_id>` claims the next pending transcode job and returns JSON with `id`, `input_url`, `filename`, `transcode`, and `delivery`.
- `GET /api/media/jobs/<job_id>/input` streams the file the worker should download.
- `POST /api/worker/jobs/<job_id>/complete` and `POST /api/worker/jobs/<job_id>/failed` are accepted as lifecycle callbacks.
- Set `MEDIA_MANAGER_AUTH_TOKEN` on the server and client to require a shared bearer token.

Queue UI:

- Filter jobs by status, source, or whether they were auto-generated from the media scan.
- Use `Cancel / Requeue` on a job to move it back to `pending`.

Transcode settings:

- Open `/settings/transcoding/` to change the pass/fail matching rule and the worker extra ffmpeg args.
- Saving the page refreshes stored metadata matches and queue state.

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
