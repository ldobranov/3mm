<script setup lang="ts">
import { defineAsyncComponent, h, computed } from 'vue';

// Props
const props = defineProps<{
  componentPath: string;
  [key: string]: any; // Allow additional props to be passed through
}>();

// Create async component that tries to load the extension component
const ExtensionComponent = defineAsyncComponent({
  loader: async () => {
    try {
      // Convert @/ alias to relative path from views directory
      const relativePath = props.componentPath.replace('@/', '../');
      const module = await import(/* @vite-ignore */ relativePath);
      return module.default;
    } catch (error) {
      console.warn(`Extension component not available: ${props.componentPath}`, error);
      // Return a fallback component
      return {
        name: 'ExtensionPlaceholder',
        props: Object.keys(props).filter(key => key !== 'componentPath'),
        render() {
          return h('div', { class: 'extension-placeholder' }, [
            h('h2', 'Extension Not Available'),
            h('p', 'The requested feature requires an extension that is not currently installed.'),
            h('p', 'Please check the Extensions panel to install the required extension.')
          ]);
        }
      };
    }
  },
  errorComponent: {
    name: 'ExtensionError',
    render() {
      return h('div', { class: 'extension-error' }, [
        h('h2', 'Extension Loading Error'),
        h('p', 'Failed to load the requested extension component.')
      ]);
    }
  },
  delay: 200,
  timeout: 3000
});

// Pass through props to the component (excluding componentPath)
const componentProps = computed(() => {
  const { componentPath, ...otherProps } = props;
  return otherProps;
});
</script>

<template>
  <ExtensionComponent v-bind="componentProps" />
</template>

<style scoped>
.extension-placeholder {
  padding: 2rem;
  text-align: center;
  color: var(--text-secondary);
}

.extension-placeholder h2 {
  color: var(--text-primary);
  margin-bottom: 1rem;
}

.extension-error {
  padding: 2rem;
  text-align: center;
  color: var(--error-text);
  background: var(--error-bg);
  border: 1px solid var(--error-border);
  border-radius: var(--border-radius-md);
}

.extension-error h2 {
  margin-bottom: 1rem;
}
</style>