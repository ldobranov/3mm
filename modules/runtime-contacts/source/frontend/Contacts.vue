<template><CrudPage :definition="definition" entity-id="contact" :language="language" /></template>
<script setup lang="ts">
import { ref,onMounted,onUnmounted } from 'vue'
import CrudPage from './CrudPage.vue'
import definition from './definition'
const language=ref('en')
const refresh=()=>{try {language.value=localStorage.getItem('preferredLanguage')||'en'}catch{language.value='en'}}
onMounted(()=>{refresh();window.addEventListener('languageChanged',refresh);window.addEventListener('storage',refresh)})
onUnmounted(()=>{window.removeEventListener('languageChanged',refresh);window.removeEventListener('storage',refresh)})
</script>
