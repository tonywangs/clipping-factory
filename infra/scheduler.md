# Cloud Run Job deployment

Replace `PROJECT_ID`, `REGION`, `BUCKET`, and `TAG` before running commands.

```bash
gcloud services enable run.googleapis.com cloudscheduler.googleapis.com firestore.googleapis.com storage.googleapis.com secretmanager.googleapis.com
gcloud firestore databases create --location=us-west1
gcloud storage buckets create gs://BUCKET --location=us-west1

# Secrets (create each once)
printf '%s' "$ANTHROPIC_API_KEY" | gcloud secrets create anthropic-api-key --data-file=-
printf '%s' "$NOTIFY_WEBHOOK_URL" | gcloud secrets create notify-webhook-url --data-file=-
printf '%s' "$YOUTUBE_API_KEY" | gcloud secrets create youtube-api-key --data-file=-
# Optional Netscape cookies file for yt-dlp on cloud IPs:
gcloud secrets create ytdlp-cookies --data-file=./cookies.txt

gcloud run jobs replace infra/cloudrun-job.yaml --region=REGION
gcloud scheduler jobs create http clipfactory-daily \
  --location=REGION --schedule='0 6 * * *' --time-zone='America/Los_Angeles' \
  --uri="https://run.googleapis.com/apis/run.googleapis.com/v1/namespaces/PROJECT_ID/jobs/clipfactory-run:run" \
  --http-method=POST --oauth-service-account-email=clipfactory-scheduler@PROJECT_ID.iam.gserviceaccount.com
```

Grant the Job service account Firestore user, Storage object admin for the chosen bucket,
and Secret Manager secret accessor. Store `ANTHROPIC_API_KEY`, optional yt-dlp cookies,
YouTube API key, and webhook URL in Secret Manager.

Cloud data-center IPs may be blocked by YouTube; ingest locally and process the stored
artifact in cloud mode when cookie/proxy handling is insufficient. A supported split is:

1. Local: `python -m clipfactory.run --episode URL --niche startup` (downloads into `raw/`)
2. Sync `raw/` + `transcripts/` to GCS
3. Cloud job processes with `STORAGE_BACKEND=gcs` using the cached objects
