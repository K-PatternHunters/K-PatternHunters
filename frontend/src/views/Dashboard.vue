<template>
  <!-- TODO: implement Dashboard UI -->
  <!--
    Sections to build:
    1. Report period selector — radio/tab: daily / weekly / monthly
    2. Domain description textarea — free-text input describing the e-commerce domain
    3. "Run Analysis" button — calls analysis.js → triggerAnalysis()
    4. Progress indicator — polls polling.js → pollJobStatus() while status === 'running'
    5. Result panel — download PPT link when status === 'done'
  -->
  <div class="dashboard">
    <p>Dashboard placeholder — implementation pending</p>
  </div>
</template>

<script setup>
// TODO: import { triggerAnalysis } from '@/api/analysis'
// TODO: import { pollJobStatus } from '@/api/polling'
// TODO: wire up reactive state (period, domainDescription, jobId, status, progress)
</script>

<style scoped>
/* TODO: add dashboard styles */
</style>
