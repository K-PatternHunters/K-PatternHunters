<template>
  <div class="dashboard-wrapper">
    <div class="bg-pattern"></div>

    <div class="dashboard-container">
      <header class="main-header">
        <div class="brand-identity">
          <img class="brand-icon" :src="brandImage" alt="PatternHunters brand" />
          <div class="brand-text">
            <h1>PatternHunters</h1>
            <p>Behavioral Intelligence Command Center</p>
          </div>
        </div>
        <div class="system-status-badge">
          <span class="status-dot active"></span>
          <span class="status-text">SYSTEM_OPERATIONAL</span>
        </div>
      </header>

      <div class="dashboard-grid">
        <aside class="control-panel">
          <section class="settings-card premium-glass">
            <h2 class="section-title">
              <span class="title-decor"></span>
              Analysis Frequency
            </h2>
            <div class="selector-group-large">
              <label v-for="p in periods" :key="p.value" :class="['selector-item-large', { selected: period === p.value }]">
                <input type="radio" v-model="period" :value="p.value" :disabled="isAnalyzing" />
                <span class="p_label">{{ p.label }}</span>
              </label>
            </div>
          </section>

          <section class="settings-card premium-glass">
            <h2 class="section-title">
              <span class="title-decor"></span>
              Domain Specification
            </h2>
            <div class="textarea-container">
              <textarea 
                v-model="domainDescription" 
                placeholder="분석 대상 도메인의 비즈니스 로직, 사용자 여정의 특이사항, 그리고 에이전트가 집중해야 할 분석 포인트를 상세히 기술하십시오."
                :disabled="isAnalyzing"
              ></textarea>
              <div class="textarea-footer">
                <span class="char-count"><strong>{{ domainDescription.length }}</strong> / 500 CHARACTERS</span>
              </div>
            </div>
          </section>

          <button 
            class="ultra-action-btn" 
            @click="startAnalysis" 
            :disabled="isAnalyzing || !domainDescription.trim()"
          >
            <span v-if="!isAnalyzing" class="btn-content">
              패턴 분석 실행
            </span>
            <span v-else class="btn-content loading">
              <span class="spinner"></span> ORCHESTRATING AGENTS...
            </span>
          </button>
        </aside>

        <main class="display-panel">
          <div v-if="!jobId && !isAnalyzing" class="massive-placeholder">
            <svg class="placeholder-icon-massive" viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
              <circle cx="50" cy="50" r="48" stroke="#E2E8F0" stroke-width="2" stroke-dasharray="10 10"/>
              <path d="M36 24H56L68 36V76H36V24Z" stroke="#CBD5E1" stroke-width="3" stroke-linejoin="round"/>
              <path d="M56 24V36H68" stroke="#CBD5E1" stroke-width="3" stroke-linejoin="round"/>
              <path d="M42 46H62M42 54H62M42 62H58" stroke="#F26522" stroke-width="2.5" stroke-linecap="round"/>
            </svg>
            <h3>AWAITING COMMAND</h3>
            <p>분석 파라미터를 설정하고 엔진을 가동하십시오.</p>
          </div>

          <transition name="super-slide">
            <div v-if="isAnalyzing || status === 'done'" class="analysis-monitor premium-glass">
              <div class="monitor-header">
                <h3>Live Orchestration Status</h3>
                <div class="job-badge">
                  <span class="label">JOB_ID</span>
                  <span class="value" v-if="jobId">{{ jobId }}</span>
                  <span class="value blinking" v-else>PENDING</span>
                </div>
              </div>

              <div class="massive-progress">
                <div class="progress-info-massive">
                  <span class="status-msg">{{ statusText }}</span>
                  <span class="percent-val">{{ progress }}%</span>
                </div>
                <div class="progress-track-massive">
                  <div class="progress-fill-massive" :style="{ width: progress + '%' }"></div>
                </div>
              </div>

              <div class="massive-console">
                <div class="console-header-bar">
                  <span class="dot red"></span><span class="dot yellow"></span><span class="dot green"></span>
                  <span class="console-title">AGENT_ORCHESTRATION_LOG</span>
                </div>
                <div class="console-content">
                  <div v-for="(log, idx) in logs" :key="idx" class="console-row">
                    <span class="timestamp">[{{ log.time }}]</span>
                    <span class="agent-tag">{{ log.agent }}</span>
                    <span class="message">{{ log.msg }}</span>
                  </div>
                </div>
              </div>

              <div v-if="status === 'done'" class="final-actions">
                <a :href="downloadUrl" class="massive-export-btn">
                  DOWNLOAD AGENTIC REPORT (PPT)
                </a>
              </div>
            </div>
          </transition>
        </main>
      </div>
    </div>

    <footer class="massive-bottom-bar">
      <div class="bar-container">
        <div class="copyright">© 2026 PATTERN HUNTERS, Inc. All rights reserved.</div>
        <div class="system-meta">
          <span>FRAMEWORK: MULTI_AGENT_RAG_v3.1</span>
          <span class="divider">|</span>
          <span>ENGINE: COGNITIVE_PATTERN_MATCHING_v5.0</span>
          <span class="divider">|</span>
          <span class="version">SYS_VER: _2.0.35</span>
        </div>
      </div>
    </footer>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import brandImage from '../image.png'

const period = ref('weekly')
const domainDescription = ref('')
const status = ref('idle') 
const progress = ref(0)
const jobId = ref(null)
const logs = ref([])
const downloadUrl = ref('#')

const isAnalyzing = computed(() => status.value === 'running')
const statusText = computed(() => {
  if (status.value === 'running') return 'AGENT_CONTEXT_AWARENESS_ACTIVE'
  if (status.value === 'done') return 'COMPLETED: CORE_INSIGHTS_EXTRACTED'
  return 'STANDBY'
})

const periods = [
  { label: '일간', value: 'daily' },
  { label: '주간', value: 'weekly' },
  { label: '월간', value: 'monthly' }
]

const startAnalysis = () => {
  status.value = 'running'
  progress.value = 0
  jobId.value = 'PH-CMD-' + Math.floor(Math.random() * 90000 + 10000)
  logs.value = []
  
  const interval = setInterval(() => {
    progress.value += Math.floor(Math.random() * 15)
    pushLog()
    if (progress.value >= 100) {
      progress.value = 100
      status.value = 'done'
      clearInterval(interval)
    }
  }, 1100)
}

const pushLog = () => {
  const agents = ["FUNNEL", "COHORT", "PERFORMANCE", "ANOMALY", "JOURNEY"]
  const steps = ["FETCHING_RAW_LOGS", "DEDUCTIVE_REASONING", "CROSS_AGENT_SYNC", "PATTERN_SYNTHESIS", "INSIGHT_GENERATION"]
  
  logs.value.unshift({
    time: new Date().toLocaleTimeString('en-GB'),
    agent: agents[Math.floor(Math.random() * agents.length)],
    msg: steps[Math.floor(Math.random() * steps.length)]
  })
}
</script>

<style scoped>
/*  */

.dashboard-wrapper {
  /* 초대형 프리미엄 테마 색상 팔레트 */
  --bg-primary: #FFFFFF;
  --bg-secondary: #F6F4F0; /* 더 따뜻하고 깊은 베이지 */
  --accent-emerald: #10b981;
  --accent-orange: #F26522; /* SK Orange */
  --accent-red: #E31937;    /* SK Red */
  --text-main: #111111;    /* 거의 검정 */
  --text-muted: #555555;    /* 짙은 회색 */
  --border-color: rgba(0, 0, 0, 0.06);
  --shadow-premium: 0 20px 50px rgba(0, 0, 0, 0.05);
  
  min-height: 100vh;
  background-color: var(--bg-secondary);
  color: var(--text-main);
  padding: 4rem 4rem 14rem 4rem; /* 하단 띠 공간을 위해 여백 대폭 증가 */
  font-family: 'Pretendard', system-ui, -apple-system, sans-serif;
  position: relative;
  overflow-x: hidden;
}

/* 배경 기하학 패턴 (디테일) */
.bg-pattern {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background-image: radial-gradient(#E2E8F0 1px, transparent 1px);
  background-size: 40px 40px;
  opacity: 0.3;
  z-index: 0;
}

.dashboard-container {
  max-width: 1600px; /* 더 넓게 설정 */
  margin: 0 auto;
  position: relative;
  z-index: 1;
}

/* Header: 웅장하고 미니멀한 전문성 */
.main-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background-color: var(--bg-primary);
  padding: 2rem 3rem;
  border-radius: 16px;
  box-shadow: var(--shadow-premium);
  border: 1px solid var(--border-color);
  margin-bottom: 5rem;
}

.brand-identity {
  display: flex;
  align-items: center;
  gap: 2.5rem;
}

.brand-icon {
  width: 96px;
  height: 96px;
  object-fit: contain;
  display: block;
}

.brand-text h1 {
  font-size: 2rem; /* 초대형 */
  font-weight: 900;
  letter-spacing: -0.02em;
  color: var(--text-main);
  margin-bottom: 0.25rem;
}

.brand-text p {
  font-size: 1rem;
  color: var(--text-muted);
  font-weight: 500;
}

.system-status-badge {
  display: flex;
  align-items: center;
  gap: 12px;
  background-color: #ECFDF5;
  padding: 1rem 2rem;
  border-radius: 50px;
  border: 1px solid #A7F3D0;
}

.status-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background-color: var(--accent-emerald);
  box-shadow: 0 0 15px var(--accent-emerald);
}

.status-text {
  font-size: 0.9rem;
  font-weight: 800;
  color: var(--accent-emerald);
  letter-spacing: 0.1em;
}

/* Grid: 더 넓은 간격 */
.dashboard-grid {
  display: grid;
  grid-template-columns: 480px 1fr; /* 좌측 패널을 더 넓게 */
  gap: 5rem;
}

/* Premium Glassmorphism Card 스타일 극대화 */
.premium-glass {
  background: rgba(255, 255, 255, 0.7);
  backdrop-filter: blur(20px);
  border: 1px solid rgba(255, 255, 255, 0.3);
  padding: 3.5rem; /* 내벽 폭 대폭 증가 */
  border-radius: 24px;
  box-shadow: var(--shadow-premium);
}

.control-panel {
  display: flex;
  flex-direction: column;
  gap: 3.5rem;
}

.section-title {
  font-size: 1.25rem;
  font-weight: 800;
  color: var(--text-main);
  text-transform: uppercase;
  letter-spacing: 0.1em;
  margin-bottom: 2rem;
  display: flex;
  align-items: center;
  gap: 12px;
}

.title-decor {
  width: 6px;
  height: 24px;
  background: linear-gradient(180deg, var(--accent-orange) 0%, var(--accent-red) 100%);
  border-radius: 3px;
}

/* Selector Group 대폭 확대 및 디자인 개선 */
.selector-group-large {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.75rem;
}

.selector-item-large {
  min-width: 0;
  background-color: var(--bg-primary);
  border: 2px solid var(--border-color);
  padding: 1rem 0.75rem;
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.3s ease;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  text-align: center;
}

.selector-item-large input { display: none; }
.selector-item-large .p_label {
  font-size: 1rem;
  font-weight: 900;
  color: var(--text-main);
  margin-bottom: 0;
}

.selector-item-large:hover:not(.selected) {
  border-color: var(--accent-orange);
  transform: translateY(-3px);
}

.selector-item-large.selected {
  background: linear-gradient(135deg, var(--accent-orange) 0%, var(--accent-red) 100%);
  border-color: transparent;
  box-shadow: 0 10px 30px rgba(242, 101, 34, 0.3);
}

.selector-item-large.selected .p_label {
  color: #FFFFFF;
}

/* Textarea 대폭 확대 및 고급화 */
.textarea-container {
  background-color: var(--bg-primary);
  border: 2px solid var(--border-color);
  border-radius: 12px;
  padding: 1.5rem;
}

textarea {
  width: 100%;
  height: 280px; /* 초대형 */
  border: none;
  background: transparent;
  color: var(--text-main);
  font-size: 1.1rem;
  line-height: 1.8;
  resize: none;
  font-family: inherit;
}

textarea:focus { outline: none; }

.textarea-footer {
  border-top: 1px solid var(--border-color);
  padding-top: 1rem;
  margin-top: 1rem;
  text-align: right;
  font-size: 0.8rem;
  color: var(--text-muted);
}

.char-count strong { color: var(--accent-orange); font-weight: 800; }

/* 초대형 액션 버튼 */
.ultra-action-btn {
  width: 100%;
  max-width: 100%;
  box-sizing: border-box;
  padding: 2.5rem; /* 초대형 */
  background: linear-gradient(135deg, var(--accent-orange) 0%, var(--accent-red) 100%);
  border: none;
  color: #FFFFFF;
  border-radius: 16px;
  cursor: pointer;
  transition: all 0.4s ease;
  box-shadow: 0 15px 40px rgba(227, 25, 55, 0.3);
  position: relative;
  overflow: hidden;
}

.ultra-action-btn .btn-content {
  font-size: 1.15rem;
  font-weight: 900;
  letter-spacing: 0.05em;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  white-space: normal;
  word-break: keep-all;
  text-align: center;
}

.ultra-action-btn:hover:not(:disabled) {
  transform: translateY(-5px);
  box-shadow: 0 20px 50px rgba(227, 25, 55, 0.4);
}

.ultra-action-btn:disabled {
  background: #CBD5E1;
  color: #94A3B8;
  cursor: not-allowed;
  box-shadow: none;
}

/* Loading 효과 강화 */
.btn-content.loading {
  opacity: 0.8;
}

.spinner {
  width: 24px;
  height: 24px;
  border: 4px solid rgba(255, 255, 255, 0.3);
  border-top-color: #FFFFFF;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* Display Panel: 더 압도적인 상태 표시 */
.display-panel {
  background-color: var(--bg-primary);
  border-radius: 24px;
  padding: 4rem; /* 내벽 폭 대폭 증가 */
  box-shadow: var(--shadow-premium);
  border: 1px solid var(--border-color);
}

.massive-placeholder {
  height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  text-align: center;
}

.placeholder-icon-massive {
  width: 200px; /* 초대형 */
  height: 200px;
  margin-bottom: 3rem;
}

.massive-placeholder h3 {
  font-size: 1.5rem;
  font-weight: 800;
  letter-spacing: 0.3em;
  color: #CBD5E1;
  margin-bottom: 1.5rem;
}

.massive-placeholder p {
  font-size: 1.1rem;
  color: #CBD5E1;
}

/* Analysis Monitor: 대형 상태 표시 */
.analysis-monitor {
  border-top: 6px solid var(--accent-orange); /* 포인트 테두리 강화 */
}

.monitor-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4rem;
}

.monitor-header h3 {
  font-size: 1.5rem;
  font-weight: 800;
}

.job-badge {
  display: flex;
  background-color: #FEE2E2;
  border-radius: 8px;
  overflow: hidden;
}

.job-badge .label {
  font-size: 0.75rem;
  font-weight: 800;
  color: #991B1B;
  padding: 0.6rem 1rem;
  background-color: #FECACA;
}

.job-badge .value {
  font-family: 'Roboto Mono', monospace;
  font-size: 0.9rem;
  font-weight: 700;
  color: var(--accent-red);
  padding: 0.6rem 1rem;
}

.job-badge .value.blinking {
  animation: blink 1.5s infinite;
}

@keyframes blink {
  0% { opacity: 1; }
  50% { opacity: 0.4; }
  100% { opacity: 1; }
}

/* 초대형 프로그레스 바 */
.massive-progress {
  margin-bottom: 4rem;
}

.progress-info-massive {
  display: flex;
  justify-content: space-between;
  font-size: 1.1rem;
  font-weight: 800;
  margin-bottom: 1.25rem;
}

.status-msg { color: var(--text-main); }
.percent-val { color: var(--accent-orange); font-size: 1.4rem; }

.progress-track-massive {
  height: 12px; /* 더 두껍게 */
  background: var(--bg-secondary);
  border-radius: 6px;
  overflow: hidden;
}

.progress-fill-massive {
  height: 100%;
  background: linear-gradient(90deg, var(--accent-orange) 0%, var(--accent-red) 100%);
  transition: width 0.5s ease;
  border-radius: 6px;
  box-shadow: 0 0 15px rgba(242, 101, 34, 0.3);
}

/* 초대형 시스템 콘솔: 터미널 디자인 고도화 */
.massive-console {
  background-color: #1A1A1A;
  border-radius: 12px;
  border: 1px solid #333;
  overflow: hidden;
}

.console-header-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  background-color: #2D2D2D;
  padding: 1rem 1.5rem;
  border-bottom: 1px solid #333;
}

.console-header-bar .dot { width: 12px; height: 12px; border-radius: 50%; }
.dot.red { background-color: #EF4444; }
.dot.yellow { background-color: #F59E0B; }
.dot.green { background-color: #10B981; }

.console-title {
  font-family: 'Roboto Mono', monospace;
  font-size: 0.8rem;
  font-weight: 700;
  color: #94A3B8;
  margin-left: 10px;
}

.console-content {
  padding: 1.5rem;
  height: 400px; /* 초대형 */
  overflow-y: auto;
  font-family: 'Roboto Mono', monospace;
  font-size: 0.95rem; /* 더 크게 */
}

.console-row { margin-bottom: 1rem; display: flex; gap: 1.5rem; }
.timestamp { color: var(--accent-emerald); font-weight: 500; }
.agent-tag {
  color: #FFFFFF;
  background-color: #334155;
  padding: 0.2rem 0.6rem;
  border-radius: 4px;
  font-size: 0.8rem;
  font-weight: 700;
}
.message { color: #E0E0E0; line-height: 1.6; }

/* 결과 액션 */
.final-actions { margin-top: 4rem; }

.massive-export-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  width: 100%;
  max-width: 100%;
  box-sizing: border-box;
  padding: 1.5rem; /* 초대형 */
  background: linear-gradient(135deg, var(--accent-orange) 0%, #D65A1E 100%);
  color: #FFFFFF;
  text-decoration: none;
  font-weight: 900;
  font-size: 1.2rem;
  letter-spacing: 0.05em;
  border-radius: 12px;
  transition: all 0.3s;
  box-shadow: 0 10px 30px rgba(242, 101, 34, 0.3);
  text-align: center;
  word-break: keep-all;
}

.massive-export-btn:hover {
  transform: translateY(-3px);
  box-shadow: 0 15px 40px rgba(242, 101, 34, 0.4);
}

/* 🆕 초대형 하단 Accent Bar: 정보 밀도 강화 */
.massive-bottom-bar {
  position: fixed;
  bottom: 0;
  left: 0;
  width: 100%;
  height: 10rem; /* 더 두껍게 설정 */
  background: linear-gradient(135deg, var(--accent-orange) 0%, var(--accent-red) 100%);
  color: #FFFFFF;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10;
  box-shadow: 0 -15px 40px rgba(0, 0, 0, 0.15);
}

.bar-container {
  width: 1600px;
  margin: 0 auto;
  padding: 0 4rem;
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
  font-size: 1rem; /* 더 크게 */
}

.system-meta {
  display: flex;
  align-items: center;
  gap: 1.5rem;
  font-family: 'Roboto Mono', monospace;
  font-size: 0.85rem;
  opacity: 0.9;
}

.system-meta .divider { opacity: 0.5; }
.system-meta .version {
  font-weight: 700;
  background-color: rgba(0, 0, 0, 0.2);
  padding: 0.4rem 0.8rem;
  border-radius: 4px;
}

/* Animations */
.super-slide-enter-active { transition: all 1s ease-out; }
.super-slide-enter-from { opacity: 0; transform: translateY(60px); }
</style>