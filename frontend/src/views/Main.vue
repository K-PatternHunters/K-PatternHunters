<template>
  <div class="command-center-wrapper">
    <aside class="side-navigation">
      <div class="nav-brand">
        <h2 class="brand-name">K-PATTERN HUNTERS</h2>
      </div>

      <nav class="nav-menu">
        <div
          v-for="item in menuItems"
          :key="item.label"
          :class="['nav-item', { active: activeMenu === item.path, disabled: !item.path }]"
          @click="navigateTo(item)"
        >
          <span class="nav-label">{{ item.label }}</span>
        </div>
      </nav>

      <div class="nav-footer">
        <div class="user-info">
          <span class="user-name">ADMIN_DEV</span>
          <span class="user-role">ROOT_ACCESS</span>
        </div>
      </div>
    </aside>

    <main class="main-viewport">
      <div class="bg-pattern-soft"></div>

      <div class="content-scroll-area">
        <header class="hero-section">
          <h1 class="service-title">
            <span class="accent-text">K-PATTERN HUNTERS</span><br />
            COGNITIVE ANALYSIS SERVICE
          </h1>
          <p class="service-desc">
            웹 앱 로그 데이터를 주간 단위로 분석하여 PPT 보고서를 자동 생성하는 멀티 에이전트 시스템입니다.
            도메인을 입력하면 퍼널 · 코호트 · 여정 · 성능 · 이상탐지 · 예측 분석을 병렬로 수행하고, 인사이트를 종합해 슬라이드로 출력합니다.
          </p>
          <button class="cta-btn" @click="goToDashboard">분석 시작하기</button>
        </header>

        <section class="feature-grid">
          <div class="feature-card" v-for="f in features" :key="f.title">
            <div class="feature-label">{{ f.label }}</div>
            <h3 class="feature-title">{{ f.title }}</h3>
            <p class="feature-desc">{{ f.desc }}</p>
          </div>
        </section>
      </div>
    </main>

    <footer class="bottom-bar">
      <div class="bar-container">
        <div class="copyright">© 2026 PATTERN HUNTERS, Inc.</div>
        <div class="meta-info">
          <span>NODE: KR-SEOUL-01</span>
          <span class="divider">/</span>
          <span>STABLE_RELEASE: v1.0</span>
        </div>
      </div>
    </footer>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'

const router = useRouter()
const route = useRoute()

const goToDashboard = () => router.push('/dashboard')

const menuItems = [
  { label: 'OVERVIEW', path: '/' },
  { label: 'REPORTS', path: '/dashboard' },
]

const activeMenu = computed(() => route.path)
const navigateTo = (item) => { if (item.path) router.push(item.path) }

const features = [
  {
    label: 'STEP 01',
    title: '도메인 컨텍스트 분석',
    desc: '분석 대상 도메인의 비즈니스 로직을 파악하고, 에이전트별 분석 설정을 자동으로 구성합니다.',
  },
  {
    label: 'STEP 02',
    title: '6개 에이전트 병렬 분석',
    desc: '퍼널 · 코호트 · 사용자 여정 · 성능 KPI · 이상 탐지 · 예측 분석을 동시에 실행합니다.',
  },
  {
    label: 'STEP 03',
    title: '인사이트 종합 및 보고서 생성',
    desc: '분석 결과를 LLM으로 종합하여 슬라이드 단위 인사이트를 추출하고 PPT 파일로 출력합니다.',
  },
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
  --border: rgba(0, 0, 0, 0.07);

  display: flex;
  height: 100vh;
  background-color: var(--bg-beige);
  font-family: 'Pretendard', sans-serif;
  overflow: hidden;
}

/* Sidebar */
.side-navigation {
  width: 200px;
  background-color: var(--bg-sidebar);
  color: white;
  display: flex;
  flex-direction: column;
  padding: 1.5rem 1rem 2.5rem;
  z-index: 20;
  flex-shrink: 0;
}

.nav-brand {
  margin-bottom: 2rem;
  padding-left: 0.75rem;
}

.brand-name {
  font-size: 0.9rem;
  font-weight: 900;
  letter-spacing: 0.08em;
  color: white;
}

.nav-menu { flex: 1; }

.nav-item {
  display: flex;
  align-items: center;
  padding: 0.7rem 1rem;
  margin-bottom: 0.2rem;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
  color: #94A3B8;
  font-weight: 700;
  font-size: 0.82rem;
  letter-spacing: 0.04em;
}

.nav-item:hover:not(.disabled),
.nav-item.active {
  background: rgba(255, 255, 255, 0.1);
  color: white;
}

.nav-item.active {
  border-left: 3px solid var(--accent-orange);
}

.nav-item.disabled {
  cursor: not-allowed;
  opacity: 0.35;
}

.nav-footer {
  border-top: 1px solid #2a2a2a;
  padding-top: 1rem;
  padding-left: 0.25rem;
}

.user-info {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.user-name {
  font-size: 0.8rem;
  font-weight: 700;
  color: #e2e8f0;
}

.user-role {
  font-size: 0.7rem;
  color: #64748b;
  letter-spacing: 0.04em;
}

/* Main */
.main-viewport {
  flex: 1;
  position: relative;
  overflow-y: auto;
  padding-bottom: 2.5rem;
}

.bg-pattern-soft {
  position: absolute;
  top: 0; left: 0; width: 100%; height: 100%;
  background-image: radial-gradient(#D1D5DB 1px, transparent 1px);
  background-size: 40px 40px;
  opacity: 0.25;
  pointer-events: none;
}

.content-scroll-area {
  max-width: 1100px;
  margin: 0 auto;
  padding: 3rem 2.5rem;
  position: relative;
  z-index: 1;
}

/* Hero */
.hero-section {
  margin-bottom: 3rem;
}

.service-title {
  font-size: 2rem;
  font-weight: 900;
  line-height: 1.15;
  letter-spacing: -0.02em;
  margin-bottom: 1.25rem;
}

.accent-text { color: var(--accent-orange); }

.service-desc {
  font-size: 0.92rem;
  color: var(--text-muted);
  line-height: 1.75;
  max-width: 640px;
  margin-bottom: 2rem;
}

.cta-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 0.75rem 1.75rem;
  background: linear-gradient(135deg, var(--accent-orange), var(--accent-red));
  color: white;
  border: none;
  border-radius: 10px;
  font-size: 0.95rem;
  font-weight: 800;
  cursor: pointer;
  box-shadow: 0 6px 20px rgba(242, 101, 34, 0.25);
  transition: all 0.2s;
}

.cta-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 10px 28px rgba(242, 101, 34, 0.35);
}

/* Feature Cards */
.feature-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1.25rem;
}

.feature-card {
  background: var(--glass-white);
  backdrop-filter: blur(16px);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 1.5rem;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.04);
}

.feature-label {
  font-size: 0.7rem;
  font-weight: 800;
  color: var(--accent-orange);
  letter-spacing: 0.1em;
  margin-bottom: 0.6rem;
}

.feature-title {
  font-size: 0.95rem;
  font-weight: 800;
  color: var(--text-main);
  margin-bottom: 0.6rem;
}

.feature-desc {
  font-size: 0.82rem;
  color: var(--text-muted);
  line-height: 1.65;
}

/* Footer */
.bottom-bar {
  position: fixed;
  bottom: 0; left: 0;
  width: 100%;
  height: 2.5rem;
  background: linear-gradient(135deg, var(--accent-orange) 0%, var(--accent-red) 100%);
  color: white;
  display: flex;
  align-items: center;
  z-index: 9;
}

.bar-container {
  width: 100%;
  padding: 0 1.5rem 0 calc(200px + 1.5rem);
  display: flex;
  justify-content: space-between;
  font-weight: 600;
  font-size: 0.75rem;
  box-sizing: border-box;
}

.meta-info {
  display: flex;
  gap: 1rem;
  font-family: 'Roboto Mono', monospace;
  font-size: 0.72rem;
  opacity: 0.9;
}
</style>
