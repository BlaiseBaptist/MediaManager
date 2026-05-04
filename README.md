# MediaManager
Runs a server that tells workers where to get, transcode, and put files it connects with Radarr and Sonarr to receive info from them when files are changed and can clean up extra files that are found on the disk and not part of any other db.
Uses `ffprobe` on all files to get up-to-date info on them.

### Worker API:

- `GET /api/worker/jobs/next?worker_id=<worker_id>` claims the next pending transcode job and returns JSON with `id`, `input_url`, `filename`, and`transcode`
- `POST /api/worker/jobs/<job_id>/complete` and `POST /api/worker/jobs/<job_id>/failed` are accepted as lifecycle callbacks.

tells the worker where to get files from lighttpd and doesnt serve them itself
