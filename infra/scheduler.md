# Cloud Run Job deployment

Replace `PROJECT_ID`, `REGION`, `BUCKET`, and `TAG` before running commands.

```bash
gcloud services enable run.googleapis.com cloudscheduler.googleapis.com firestore.googleapis.com storage.googleapis.com secretmanager.googleapis.com
gcloud firestore databases create --location=us-west1
gcloud storage buckets create gs://BUCKET --location=us-west1
gcloud run jobs replace infra/cloudrun-job.yaml --region=REGION
gcloud scheduler jobs create http clipfactory-daily \
  --location=REGION --schedule='0 6 * * *' --time-zone='America/Los_Angeles' \
  --uri="https://run.googleapis.com/apis/run.googleapis.com/v1/namespaces/PROJECT_ID/jobs/clipfactory-run:run" \
  --http-method=POST --oauth-service-account-email=clipfactory-scheduler@PROJECT_ID.iam.gserviceaccount.com
```

Grant the Job service account Firestore user, Storage object admin for the chosen bucket,
and Secret Manager secret accessor. Store `ANTHROPIC_API_KEY`, optional yt-dlp cookies,
and webhook URL in Secret Manager. Cloud data-center IPs may be blocked by YouTube; ingest
locally and process the stored artifact in cloud mode when cookie/proxy handling is insufficient.
