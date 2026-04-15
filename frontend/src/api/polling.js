import client from './client.js'

/**
 * GET /analysis/status/{jobId}
 * @param {string} jobId
 * @returns {Promise<{ job_id: string, status: string, progress: number, result_url: string|null, error: string|null }>}
 */
export async function getJobStatus(jobId) {
  const { data } = await client.get(`/analysis/status/${jobId}`)
  return data
}
