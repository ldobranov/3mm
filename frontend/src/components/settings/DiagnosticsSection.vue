<template>
  <SettingsSection :title="t('diagnostics.title', 'Support diagnostics')">
    <DiagnosticWorkspace />
  </SettingsSection>
</template>

<script setup lang="ts">
import SettingsSection from '@/components/SettingsSection.vue'
import DiagnosticWorkspace from './DiagnosticWorkspace.vue'
import { useI18n } from '@/utils/i18n'
const { t } = useI18n()
</script>
