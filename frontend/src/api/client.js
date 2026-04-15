import axios from 'axios'

const BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

export default axios.create({
  baseURL: BASE,
  headers: { 'Content-Type': 'application/json' },
})
