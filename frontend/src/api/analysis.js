import client from './client.js'

/**
 * POST /analysis/run
 * @param {{ period: string, domain_description: string, week_start: string, week_end: string, log_ids: string[] }} payload
 * @returns {Promise<{ job_id: string }>}
 */
export async function triggerAnalysis(payload) {
  const { data } = await client.post('/analysis/run', payload)
  return data
}
