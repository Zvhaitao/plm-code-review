import axios from 'axios'

const TOKEN_KEY = 'plm_token'

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || '',
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY)
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (resp) => resp,
  (error) => {
    if (error.response?.status === 401 && !location.pathname.startsWith('/login')) {
      localStorage.removeItem(TOKEN_KEY)
      location.href = '/login'
    }
    return Promise.reject(error)
  },
)

export const auth = {
  setToken: (t: string) => localStorage.setItem(TOKEN_KEY, t),
  getToken: () => localStorage.getItem(TOKEN_KEY),
  clear: () => localStorage.removeItem(TOKEN_KEY),
}

// --- 类型 ---
export interface Repository {
  id: number
  gitea_owner: string
  gitea_name: string
  local_path: string
  branch: string
  last_reviewed_sha: string
  enabled: boolean
  review_rules: string
  created_at: string
}

export interface Finding {
  id: number
  file_path: string
  line: number | null
  severity: string
  category: string
  message: string
  suggestion: string
  existing_code: string
}

export interface Review {
  id: number
  repository_id: number
  repository_name: string
  commit_sha: string
  commit_message: string
  commit_author: string
  status: string
  stage: string
  stage_detail: string
  tool_summary: string
  trigger: string
  model: string
  summary: string
  score: number | null
  error: string
  created_at: string
  finished_at: string | null
}

export interface LintIssue {
  id: number
  file_path: string
  line: number | null
  column: number | null
  rule_id: string
  severity: string // error / warning
  message: string
  on_changed_line: boolean
  rule_desc: string
  rule_url: string
  code_context: string
  context_start: number | null
}

export interface ReviewDetail extends Review {
  findings: Finding[]
  lint_issues: LintIssue[]
}

export interface ReviewFacets {
  repositories: { id: number; name: string; review_count: number }[]
  authors: { name: string; review_count: number }[]
  pending_count: number
}

export interface FileDiff {
  path: string
  old_path: string
  status: string // added / modified / deleted / renamed
  additions: number
  deletions: number
  patch: string
  binary: boolean
  truncated: boolean
}

export interface CommitDiff {
  sha: string
  parent_sha: string
  author: string
  message: string
  files_changed: number
  insertions: number
  deletions: number
  files: FileDiff[]
}
