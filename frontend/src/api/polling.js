// Polls the backend for the current status of an analysis job by job_id.

// TODO: implement pollJobStatus(jobId) — GET /analysis/status/{job_id}
// Returns: { status: 'pending' | 'running' | 'done' | 'failed', progress: number, result_url?: string }
// Use exponential back-off between polls.
