<template>
  <div class="sample-widget" :style="widgetStyle">
    <h3>{{ config.message || 'Hello from extension!' }}</h3>
    <p>This is a sample extension widget</p>
  </div>
</template>

<script>
export default {
  name: 'SampleWidget',
  props: {
    config: {
      type: Object,
      default: () => ({})
    }
  },
  computed: {
    widgetStyle() {
      return {
        backgroundColor: this.config.color || '#007bff',
        color: 'white',
        padding: '1rem',
        borderRadius: '8px',
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        alignItems: 'center',
        textAlign: 'center'
      };
    }
  }
}
</script>