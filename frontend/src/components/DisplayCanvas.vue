<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, watch } from 'vue';
import { GridStack, type GridStackNode } from 'gridstack';
import 'gridstack/dist/gridstack.min.css';

import { createApp, type App as VueApp } from 'vue';
import ExtensionWidget from '@/components/widgets/ExtensionWidget.vue';

interface Item {
  id: number;
  x: number;
  y: number;
  width: number;
  height: number;
  type: string; // Allow extension types
  config: any;
}

const props = defineProps<{
  widgets: Item[];
  editable?: boolean;
}>();

const emit = defineEmits<{
  (e: 'layoutChanged', items: Array<{ id: number; x: number; y: number; width: number; height: number; z_index: number }>): void;
  (e: 'deleteWidget', id: number): void;
  (e: 'editWidget', id: number): void;
  (e: 'addFromDrop', payload: { type: Item['type']; x: number; y: number; width: number; height: number }): void;
}>();

const gridEl = ref<HTMLElement | null>(null);
let grid: GridStack | null = null;
let changeDebounce: number | null = null;
let updating = false;

// track mounted Vue apps per widget id
const mountedApps = new Map<number, VueApp>();

function widgetComponentFor(type: Item['type']) {
  // All widgets are now extensions
  return ExtensionWidget;
}

function minConstraintsFor(type: Item['type']) {
  // Default constraints for all widgets
  return { minW: 2, minH: 1 };
}

function cleanupMounted() {
  mountedApps.forEach(app => { try { app.unmount(); } catch { /* noop */ } });
  mountedApps.clear();
}

function emitChanges(items: GridStackNode[]) {
  const mapped = items.map((i) => ({
    id: Number(i.id || (i.el?.getAttribute('gs-id') || '0')),
    x: i.x!,
    y: i.y!,
    width: i.w!,
    height: i.h!,
    z_index: 1,
  }));
  emit('layoutChanged', mapped);
}

function renderItems() {
  if (!grid || updating) return;
  updating = true;

  try {
    (grid as any).batchUpdate?.();

    // Build nodes with sizing + id; content injected after
    const nodes: GridStackNode[] = props.widgets.map((w) => ({
      id: String(w.id),
      x: w.x,
      y: w.y,
      w: w.width,
      h: w.height,
    })) as any;

    grid.load(nodes, true);

    // After load, mount Vue widgets; fallback inject DOM if content isn't present
    setTimeout(() => {
      cleanupMounted();

      const nodesNow = (grid as any).engine.nodes as GridStackNode[];
      for (const n of nodesNow) {
        const id = Number(n.id || 0);
        const widget = props.widgets.find((w) => w.id === id);
        if (!widget) continue;

        const el = n.el as HTMLElement | undefined;
        if (!el) continue;

        // Apply min constraints in editable mode
        if (props.editable !== false) {
          const { minW, minH } = minConstraintsFor(widget.type);
          try { (grid as any).update(n, { minW, minH }); } catch { /* ignore */ }
        }

        // Ensure exactly one content container
        let content = el.querySelector('.grid-stack-item-content') as HTMLElement | null;
        if (!content) {
          content = document.createElement('div');
          content.className = 'grid-stack-item-content bg-gray-800 rounded p-2 text-black relative grid-no-drag';
          content.style.overflow = 'hidden'; // Prevent scrollbars
          content.style.borderRadius = 'var(--border-radius-md)'; // Ensure border radius
          el.appendChild(content);
        }

        // Toolbar: only in editable mode
        if (props.editable !== false) {
          let toolbar = content.querySelector('[data-toolbar="1"]') as HTMLElement | null;
          if (!toolbar) {
            toolbar = document.createElement('div');
            toolbar.setAttribute('data-toolbar', '1');
            toolbar.className = 'absolute top-1 right-1 flex gap-1 items-center';
            // ensure toolbar is on top of resizable handles
            toolbar.style.zIndex = '5';
            toolbar.innerHTML = `
              <button class="px-1 text-xs bg-yellow-600 rounded text-black" data-action="edit">✎</button>
              <button class="px-1 text-xs bg-red-600 rounded text-black" data-action="delete">×</button>
            `;
            content.appendChild(toolbar);
          }
          toolbar.onclick = (evt: MouseEvent) => {
            const target = evt.target as HTMLElement;
            const action = target?.getAttribute('data-action');
            if (action === 'delete') emit('deleteWidget', widget.id);
            if (action === 'edit') emit('editWidget', widget.id);
          };
        } else {
        // read-only: remove toolbar if any
        const existing = content.querySelector('[data-toolbar="1"]');
        if (existing) existing.remove();
        }

        // Root mount container
        let root = content.querySelector('[data-widget-root="1"]') as HTMLElement | null;
        if (!root) {
          root = document.createElement('div');
          root.setAttribute('data-widget-root', '1');
          content.appendChild(root);
        }

        // Mount Vue widget component
        const Comp = widgetComponentFor(widget.type);
        const componentProps: any = { config: widget.config };

        // All widgets are now extensions
        if (widget.type.startsWith('extension:')) {
          const extensionId = parseInt(widget.type.split(':')[1]);
          componentProps.extensionId = extensionId;
          componentProps.extensionName = widget.type; // This is the full type like "extension:1"
          componentProps.width = widget.width;
          componentProps.height = widget.height;
        } else {
          // Legacy widget types - map to extension IDs (will be set after installation)
          // For now, treat as extension widgets
          componentProps.extensionId = 0; // Placeholder
          componentProps.extensionName = widget.type;
          componentProps.width = widget.width;
          componentProps.height = widget.height;
        }

        const app = createApp(Comp, componentProps);
        app.mount(root);
        mountedApps.set(widget.id, app);
      }
    }, 0);
  } finally {
    (grid as any).commit?.();
    updating = false;
  }
}

// Shallow projection for change detection including config marker
let prevProjection: Array<{ id: number; x: number; y: number; width: number; height: number; _cv: string }> = [];
let rerenderTimer: number | null = null;

watch(
  () => props.widgets.map(w => ({
    id: w.id,
    x: w.x,
    y: w.y,
    width: w.width,
    height: w.height,
    _cv: JSON.stringify(w.config ?? {}),
  })),
  (now) => {
    const changed =
      now.length !== prevProjection.length ||
      now.some((n, i) => {
        const p = prevProjection[i];
        return (
          !p ||
          n.id !== p.id ||
          n.x !== p.x ||
          n.y !== p.y ||
          n.width !== p.width ||
          n.height !== p.height ||
          n._cv !== p._cv
        );
      });

    if (!changed) return;
    prevProjection = now.slice();

    if (rerenderTimer) window.clearTimeout(rerenderTimer);
    rerenderTimer = window.setTimeout(() => {
      renderItems();
    }, 100);
  },
  { deep: false }
);

onMounted(() => {
  if (props.editable === false) {
    grid = GridStack.init(
      {
        float: true,
        cellHeight: 120,
        column: 12,
        margin: 8,
        disableDrag: true,
        disableResize: true,
      },
      gridEl.value!
    );
  } else {
    grid = GridStack.init(
      {
        float: true,
        cellHeight: 120,
        column: 12,
        margin: 8,
        disableDrag: false,
        disableResize: false,
        draggable: true,
        resizable: { handles: 'se' },
        acceptWidgets: true,
      } as any,
      gridEl.value!
    );
  }

  renderItems();

  grid.on('change', (_e, items) => {
    if (!items || !items.length) return;

    // Detect new nodes (no gs-id attribute yet) and emit addFromDrop to persist
    const newlyAdded: GridStackNode[] = items.filter(n => {
      const el = n && (n.el as HTMLElement | undefined);
      return !!(el && !el.getAttribute('gs-id'));
    });
    if (newlyAdded.length) {
      newlyAdded.forEach(n => {
        const el = n.el as HTMLElement;
        const type = (el.dataset.type as Item['type']) || 'TEXT';
        emit('addFromDrop', { type, x: n.x!, y: n.y!, width: n.w!, height: n.h! });
      });
      return; // don't emit layoutChanged for this batch; persistence will re-render
    }

    if (changeDebounce) window.clearTimeout(changeDebounce);
    changeDebounce = window.setTimeout(() => emitChanges(items), 200);
  });
});

onBeforeUnmount(() => {
  cleanupMounted();
  setTimeout(() => {
    grid?.destroy(false);
    grid = null;
  }, 0);
});
</script>

<template>
  <div ref="gridEl" class="grid-stack"></div>
</template>