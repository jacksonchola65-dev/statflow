import api from './api'

const BASE = '/auth'

/**
 * POST /auth/login
 * @param {string} email
 * @param {string} password
 * @returns {Promise<{ user: object, expires_in: number, csrf_token: string }>}
 */
export async function login(email, password) {
  const { data } = await api.post(`${BASE}/login`, { email, password })
  return data
}

/**
 * GET /auth/me
 * Probes the current session — returns the active user if authenticated.
 * @returns {Promise<{ user: object, csrf_token: string }>}
 */
export async function getCurrentUser() {
  const { data } = await api.get(`${BASE}/me`)
  return data
}

/**
 * POST /auth/logout
 * Clears server-side cookies. Tolerates 401 (stale session).
 */
export async function logout() {
  try {
    await api.post(`${BASE}/logout`)
  } catch (error) {
    // A 401 on logout is fine — session was already expired
    if (error?.response?.status !== 401) {
      throw error
    }
  }
}
