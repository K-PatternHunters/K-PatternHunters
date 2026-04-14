<template>
  <div class="command-center-wrapper">
    <aside class="side-navigation premium-glass-dark">
      <div class="nav-brand">
        <h2 class="brand-name">K-PATTERN HUNTERS</h2>
      </div>
      
      <nav class="nav-menu">
        <div v-for="item in menuItems" :key="item.label" :class="['nav-item', { active: item.active }]">
          <span class="nav-label">{{ item.label }}</span>
        </div>
      </nav>

      <div class="nav-footer">
        <div class="user-profile">
          <div class="user-info">
            <span class="user-name">ADMIN_DEV</span>
            <span class="user-role">ROOT_ACCESS</span>
          </div>
        </div>
      </div>
    </aside>

    <main class="main-viewport">
      <div class="bg-pattern-soft"></div>

      <div class="content-scroll-area">
        <header class="service-hero-section">
          <div class="hero-content">
            <h1 class="service-title">
              <span class="accent-text">PATTERN HUNTERS</span><br />
              COGNITIVE ANALYSIS COMMAND
            </h1>
            <p class="service-desc">
              멀티 에이전트 오케스트레이션을 통한 실시간 사용자 행동 패턴 및 비정상 징후 탐지 시스템입니다.<br />
              복잡한 로그 데이터에서 비즈니스 인사이트를 추출하고 최적의 의사결정 경로를 제안합니다.
            </p>
          </div>
          <div class="system-time-box">
            <span class="label">LAST_SYNC_TIME</span>
            <span class="value">2026-04-13 18:50:48</span>
          </div>
        </header>

        <div class="dashboard-grid">
          <section class="quick-access-card premium-gradient">
            <h3>NEW_PROJECT_INITIALIZE</h3>
            <p>분석 대상 도메인을 설정하여 새로운 에이전트 군집을 생성하십시오.</p>
            <button type="button" class="massive-white-btn" @click="goToDashboard">
              대시보드에서 분석 시작
            </button>
          </section>

          <section class="activity-log premium-glass">
            <div class="section-header">
              <h3>LIVE_AGENT_ACTIVITY</h3>
              <span class="live-tag">LIVE</span>
            </div>
            <div class="log-container">
              <div v-for="(log, idx) in activityLogs" :key="idx" class="log-entry">
                <span class="t-stamp">{{ log.time }}</span>
                <span class="a-name">[{{ log.agent }}]</span>
                <span class="msg">{{ log.msg }}</span>
              </div>
            </div>
          </section>
        </div>

        <section class="metrics-grid">
          <div v-for="stat in systemStats" :key="stat.label" class="metric-card premium-glass">
            <div class="metric-header">
              <span class="label">{{ stat.label }}</span>
            </div>
            <div class="metric-body">
              <span class="value">{{ stat.value }}</span>
              <span :class="['trend', stat.trend]">
                {{ stat.trend === 'up' ? '+' : '-' }}{{ stat.percent }}%
              </span>
            </div>
          </div>
        </section>
      </div>
    </main>

    <footer class="massive-bottom-bar">
      <div class="bar-container">
        <div class="copyright">© 2026 PATTERN HUNTERS, Inc.</div>
        <div class="meta-info">
          <span>NODE: KR-SEOUL-01</span>
          <span class="divider">/</span>
          <span>STABLE_REALEASE: _2.0.35</span>
        </div>
      </div>
    </footer>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'

const router = useRouter()

const goToDashboard = () => {
  router.push('/dashboard')
}

const menuItems = [
  { label: 'OVERVIEW', active: true },
  { label: 'REPORTS', active: false },
  { label: 'SETTINGS', active: false },
]

const systemStats = [
  { label: 'TOTAL_SESSIONS', value: '142,892', trend: 'up', percent: '12.5' },
  { label: 'MATCH_PRECISION', value: '99.2%', trend: 'up', percent: '0.4' },
  { label: 'DETECTION_ALERTS', value: '08', trend: 'down', percent: '22.1' }
]

const activityLogs = [
  { time: '18:50:21', agent: 'JOURNEY', msg: 'Mobile checkout path synchronized.' },
  { time: '18:49:55', agent: 'ANOMALY', msg: 'Subtle latency spike detected in API_v2.' },
  { time: '18:48:12', agent: 'FUNNEL', msg: 'Data fetching from production-db completed.' }
]
</script>

<style scoped>
.command-center-wrapper {
  --bg-beige: #F5F3ED;
  --bg-sidebar: #111111;
  --accent-orange: #F26522;
  --accent-red: #E31937;
  --text-main: #1A1A1A;
  --text-muted: #6B7280;
  --glass-white: rgba(255, 255, 255, 0.75);
  --accent-emerald: #10b981;
  
  display: flex;
  height: 100vh;
  background-color: var(--bg-beige);
  font-family: 'Pretendard', sans-serif;
  overflow: hidden;
}

/* 1. Sidebar Styling */
.side-navigation {
  width: 320px;
  background-color: var(--bg-sidebar);
  color: white;
  display: flex;
  flex-direction: column;
  padding: 3rem 1.5rem;
  z-index: 20;
}

.nav-brand {
  margin-bottom: 5rem;
  padding-left: 1rem;
}

.brand-name { font-size: 1.4rem; font-weight: 900; letter-spacing: 0.1em; }

.nav-menu { flex: 1; }
.nav-item {
  display: flex;
  align-items: center;
  padding: 1.2rem 1.5rem;
  margin-bottom: 0.5rem;
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.3s;
  color: #94A3B8;
  font-weight: 700;
}

.nav-item:hover, .nav-item.active {
  background: rgba(255, 255, 255, 0.1);
  color: white;
}

.nav-item.active {
  border-left: 4px solid var(--accent-orange);
}

.nav-footer {
  border-top: 1px solid #333;
  padding-top: 2rem;
}

.user-profile {
  display: flex;
  align-items: center;
}

.user-info {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

/* 2. Main Content Styling */
.main-viewport {
  flex: 1;
  position: relative;
  overflow-y: auto;
  padding-bottom: 12rem; /* 하단 바 공간 */
}

.bg-pattern-soft {
  position: absolute; top: 0; left: 0; width: 100%; height: 100%;
  background-image: radial-gradient(#D1D5DB 1px, transparent 1px);
  background-size: 40px 40px;
  opacity: 0.3;
}

.content-scroll-area {
  max-width: 1400px;
  margin: 0 auto;
  padding: 5rem 3rem;
  position: relative;
  z-index: 1;
}

/* Header Section: 서비스 설명 */
.service-hero-section {
  margin-bottom: 5rem;
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
}

.service-title {
  font-size: 3rem;
  font-weight: 900;
  line-height: 1.1;
  letter-spacing: -0.02em;
  margin-bottom: 1.5rem;
}

.accent-text { color: var(--accent-orange); }

.service-desc {
  font-size: 1.15rem;
  color: var(--text-muted);
  line-height: 1.8;
  max-width: 700px;
}

.system-time-box {
  text-align: right;
  font-family: 'Roboto Mono', monospace;
}

.system-time-box .label { font-size: 0.75rem; color: var(--text-muted); display: block; }
.system-time-box .value { font-size: 1rem; font-weight: 700; color: var(--accent-red); }

/* Metrics: LIVE 영역 아래 배치 */
.metrics-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 2.5rem;
  margin-top: 4rem;
  margin-bottom: 4rem;
}

.metric-card {
  background: var(--glass-white);
  backdrop-filter: blur(20px);
  padding: 2.5rem;
  border-radius: 20px;
  border: 1px solid rgba(0,0,0,0.05);
  box-shadow: 0 15px 35px rgba(0,0,0,0.05);
}

.metric-header { margin-bottom: 1rem; }
.metric-header .label { font-size: 0.85rem; font-weight: 800; color: var(--text-muted); letter-spacing: 0.05em; }

.metric-body { display: flex; justify-content: space-between; align-items: baseline; }
.metric-body .value { font-size: 2.2rem; font-weight: 900; }
.trend { font-size: 0.9rem; font-weight: 800; }
.trend.up { color: var(--accent-emerald); }
.trend.down { color: var(--accent-red); }

/* Dashboard Grid */
.dashboard-grid {
  display: grid;
  grid-template-columns: 400px 1fr;
  gap: 3rem;
}

.premium-glass {
  background: var(--glass-white);
  backdrop-filter: blur(20px);
  padding: 3rem;
  border-radius: 24px;
  border: 1px solid rgba(0,0,0,0.05);
}

.section-header { display: flex; justify-content: space-between; margin-bottom: 2rem; }
.live-tag {
  background: var(--accent-red);
  color: white;
  padding: 0.3rem 0.8rem;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 900;
}

.log-container {
  background: #1A1A1A;
  border-radius: 12px;
  padding: 1.5rem;
  height: 250px;
  overflow-y: auto;
  font-family: 'Roboto Mono', monospace;
  font-size: 0.9rem;
}

.log-entry { margin-bottom: 0.8rem; display: flex; gap: 15px; }
.t-stamp { color: var(--accent-emerald); }
.a-name { color: #AAA; }
.msg { color: #EEE; }

.premium-gradient {
  background: linear-gradient(135deg, var(--accent-orange), var(--accent-red));
  padding: 3.5rem;
  border-radius: 24px;
  color: white;
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.massive-white-btn {
  background: white; color: var(--accent-red); border: none;
  padding: 1.5rem; border-radius: 12px;
  font-size: 1.1rem; font-weight: 900; margin-top: 2rem;
  cursor: pointer;
  box-shadow: 0 10px 20px rgba(0,0,0,0.1);
}

/* Footer Accent Bar */
.massive-bottom-bar {
  position: fixed; bottom: 0; left: 320px; right: 0; height: 8rem;
  background: linear-gradient(135deg, var(--accent-orange) 0%, var(--accent-red) 100%);
  color: white; display: flex; align-items: center; z-index: 10;
}

.bar-container {
  width: 100%; max-width: 1400px; margin: 0 auto; padding: 0 3rem;
  display: flex; justify-content: space-between; font-weight: 700;
}

.meta-info { display: flex; gap: 1rem; font-family: 'Roboto Mono', monospace; font-size: 0.85rem; opacity: 0.9; }
</style>    