<template>
  <Teleport to="body">
    <div 
      v-if="isOpen" 
      class="command-palette-overlay"
      @click="close"
    >
      <div 
        class="command-palette"
        @click.stop
      >
        <div class="command-input-wrapper">
          <i class="bi bi-search"></i>
          <input
            ref="searchInput"
            v-model="searchQuery"
            type="text"
            class="command-input"
            placeholder="Type a command or search..."
            @keydown.escape="close"
            @keydown.enter="executeSelected"
            @keydown.up.prevent="navigateUp"
            @keydown.down.prevent="navigateDown"
          >
          <kbd class="escape-hint">ESC</kbd>
        </div>
        
        <div class="command-results">
          <div v-if="filteredCommands.length === 0" class="no-results">
            No results found for "{{ searchQuery }}"
          </div>
          
          <div 
            v-for="(group, index) in groupedCommands" 
            :key="group.category"
            v-show="group.commands.length > 0"
          >
            <div class="command-category">{{ group.category }}</div>
            <div
              v-for="(command, cmdIndex) in group.commands"
              :key="command.id"
              class="command-item"
              :class="{ selected: isSelected(group.category, cmdIndex) }"
              @click="execute(command)"
              @mouseenter="setSelected(group.category, cmdIndex)"
            >
              <i :class="command.icon" class="command-icon"></i>
              <div class="command-info">
                <div class="command-title">{{ command.title }}</div>
                <div v-if="command.description" class="command-description">
                  {{ command.description }}
                </div>
              </div>
              <div v-if="command.shortcut" class="command-shortcut">
                <kbd v-for="key in command.shortcut.split('+')" :key="key">{{ key }}</kbd>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script lang="ts">
import { defineComponent, ref, computed, onMounted, onUnmounted, nextTick } from 'vue';
import { useRouter } from 'vue-router';
import { useThemeStore } from '@/stores/theme';
import { useI18n } from '@/utils/i18n';
import { isMenuRouteEligible, isNavigationItemVisible, localizedNavigationLabel } from '@/utils/menu-navigation';
import { kioskRouteAvailable } from '@/utils/kiosk-session';

interface Command {
  id: string;
  title: string;
  description?: string;
  category: string;
  icon: string;
  action: () => void;
  shortcut?: string;
  keywords?: string[];
}

export default defineComponent({
  name: 'CommandPalette',
  setup() {
    const router = useRouter();
    const themeStore = useThemeStore();
    const { t, currentLanguage } = useI18n();
    const registryGeneration = ref(0);
    const isOpen = ref(false);
    const searchQuery = ref('');
    const searchInput = ref<HTMLInputElement>();
    const selectedCategory = ref('');
    const selectedIndex = ref(0);
    
    // Read the current registry/actor each time the palette opens. Installing or
    // removing an application needs no product command branch in Core.
    const commands = computed<Command[]>(() => {
      void registryGeneration.value;
      const role = localStorage.getItem('role') || '';
      const signedIn = Boolean(localStorage.getItem('authToken'));
      const cmds: Command[] = [{ id: 'nav-home', title: t('palette.home', 'Go to Home'),
        category: 'Navigation', icon: 'bi bi-house', action: () => router.push('/'), shortcut: 'Alt+H' }];
      for (const route of router.getRoutes()) {
        if (!isMenuRouteEligible(route.path, route.meta.requiresRole as string | undefined, role)) continue;
        const audience = route.meta.applicationAudience;
        const kiosk = kioskRouteAvailable(route.meta.compiledModuleId);
        if ((route.meta.requiresKiosk || audience === 'kiosk') && !kiosk) continue;
        const item = { path: route.path, label: (route.meta.menuLabel || String(route.name || route.path)) as string | Record<string, string>,
          audience: (audience === 'administrator' ? 'admin' : audience === 'operator' ? 'authenticated' : audience) as 'public' | 'authenticated' | 'admin' | 'kiosk' | undefined };
        if (!isNavigationItemVisible(item, { isLoggedIn: signedIn, isKiosk: kiosk, currentRole: role,
          routeRequiresAuth: route.meta.requiresAuth === true, routeRequiredRole: route.meta.requiresRole as string | undefined })) continue;
        const translations = (item.label as { translations?: Record<string, string> }).translations;
        const label = typeof route.meta.menuLabelKey === 'string'
          ? t(route.meta.menuLabelKey, localizedNavigationLabel(item.label, currentLanguage.value))
          : translations?.[currentLanguage.value] || localizedNavigationLabel(item.label, currentLanguage.value);
        cmds.push({ id: `route-${route.path}`, title: `${t('palette.goTo', 'Go to')} ${label}`,
          category: 'Navigation', icon: 'bi bi-arrow-right', keywords: [route.path],
          action: () => router.push(route.path), shortcut: route.name === 'Settings' ? 'Alt+S' : undefined });
      }
      if (signedIn) cmds.push({ id: 'action-logout', title: t('menu.logout', 'Logout'),
        category: 'Actions', icon: 'bi bi-box-arrow-right', action: () => router.push('/user/logout'), shortcut: 'Ctrl+Shift+L' });
      cmds.push({ id: 'theme-toggle', title: t('palette.theme', 'Toggle Dark Mode'),
        category: 'Theme', icon: 'bi bi-moon', action: () => toggleDarkMode() },
        { id: 'help-shortcuts', title: t('palette.shortcuts', 'Keyboard Shortcuts'),
          category: 'Help', icon: 'bi bi-keyboard', action: () => showShortcuts() });
      return cmds;
    });

    // Filter commands based on search query
    const filteredCommands = computed(() => {
      if (!searchQuery.value) {
        return commands.value;
      }
      
      const query = searchQuery.value.toLowerCase();
      return commands.value.filter(cmd => {
        const inTitle = cmd.title.toLowerCase().includes(query);
        const inDescription = cmd.description?.toLowerCase().includes(query);
        const inKeywords = cmd.keywords?.some(k => k.toLowerCase().includes(query));
        return inTitle || inDescription || inKeywords;
      });
    });
    
    // Group commands by category
    const groupedCommands = computed(() => {
      const groups: { [key: string]: Command[] } = {};
      
      filteredCommands.value.forEach(cmd => {
        if (!groups[cmd.category]) {
          groups[cmd.category] = [];
        }
        groups[cmd.category].push(cmd);
      });
      
      // Convert to array and sort categories
      const categoryOrder = ['Actions', 'Navigation', 'Theme', 'Help'];
      return categoryOrder
        .filter(cat => groups[cat])
        .map(cat => ({
          category: cat,
          commands: groups[cat]
        }));
    });
    
    // Check if item is selected
    const isSelected = (category: string, index: number) => {
      return selectedCategory.value === category && selectedIndex.value === index;
    };
    
    // Set selected item
    const setSelected = (category: string, index: number) => {
      selectedCategory.value = category;
      selectedIndex.value = index;
    };
    
    // Navigate up in results
    const navigateUp = () => {
      const groups = groupedCommands.value;
      if (groups.length === 0) return;
      
      const catIndex = groups.findIndex(g => g.category === selectedCategory.value);
      
      if (catIndex === -1) {
        // Select last item
        const lastGroup = groups[groups.length - 1];
        setSelected(lastGroup.category, lastGroup.commands.length - 1);
        return;
      }
      
      if (selectedIndex.value > 0) {
        selectedIndex.value--;
      } else if (catIndex > 0) {
        // Move to previous category
        const prevGroup = groups[catIndex - 1];
        setSelected(prevGroup.category, prevGroup.commands.length - 1);
      } else {
        // Wrap to last item
        const lastGroup = groups[groups.length - 1];
        setSelected(lastGroup.category, lastGroup.commands.length - 1);
      }
    };
    
    // Navigate down in results
    const navigateDown = () => {
      const groups = groupedCommands.value;
      if (groups.length === 0) return;
      
      const catIndex = groups.findIndex(g => g.category === selectedCategory.value);
      
      if (catIndex === -1) {
        // Select first item
        setSelected(groups[0].category, 0);
        return;
      }
      
      const currentGroup = groups[catIndex];
      
      if (selectedIndex.value < currentGroup.commands.length - 1) {
        selectedIndex.value++;
      } else if (catIndex < groups.length - 1) {
        // Move to next category
        setSelected(groups[catIndex + 1].category, 0);
      } else {
        // Wrap to first item
        setSelected(groups[0].category, 0);
      }
    };
    
    // Execute selected command
    const executeSelected = () => {
      const group = groupedCommands.value.find(g => g.category === selectedCategory.value);
      if (group && group.commands[selectedIndex.value]) {
        execute(group.commands[selectedIndex.value]);
      }
    };
    
    // Execute a command
    const execute = (command: Command) => {
      command.action();
      close();
    };
    
    // Toggle dark mode
    const toggleDarkMode = () => {
      themeStore.toggleTheme();
    };
    
    // Show shortcuts modal
    const showShortcuts = () => {
      alert(['Ctrl+K: ' + t('palette.open', 'Command Palette'),
        ...commands.value.filter(command => command.shortcut).map(command => `${command.shortcut}: ${command.title}`)].join('\n'));
    };

    // Open command palette
    const open = async () => {
      isOpen.value = true;
      searchQuery.value = '';
      selectedCategory.value = '';
      selectedIndex.value = 0;
      
      ++registryGeneration.value;
      await nextTick();
      searchInput.value?.focus();
    };
    
    // Close command palette
    const close = () => {
      isOpen.value = false;
    };
    
    // Global keyboard shortcuts
    const handleKeydown = (e: KeyboardEvent) => {
      // Ctrl+K or Cmd+K to open command palette
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        if (isOpen.value) {
          close();
        } else {
          open();
        }
      }
      
      if (!isOpen.value) {
        ++registryGeneration.value;
        const shortcut = e.altKey && e.key.toLowerCase() === 'h' ? 'Alt+H'
          : e.altKey && e.key.toLowerCase() === 's' ? 'Alt+S'
            : e.ctrlKey && e.shiftKey && e.key.toLowerCase() === 'l' ? 'Ctrl+Shift+L' : '';
        const command = commands.value.find(item => item.shortcut === shortcut && shortcut);
        if (command) { e.preventDefault(); command.action(); }
      }
    };

    onMounted(() => {
      document.addEventListener('keydown', handleKeydown);
    });
    
    onUnmounted(() => {
      document.removeEventListener('keydown', handleKeydown);
      if ((window as any).openCommandPalette === open) delete (window as any).openCommandPalette;
    });
    
    // Expose for external use
    (window as any).openCommandPalette = open;
    
    return {
      isOpen,
      searchQuery,
      searchInput,
      filteredCommands,
      groupedCommands,
      selectedCategory,
      selectedIndex,
      isSelected,
      setSelected,
      navigateUp,
      navigateDown,
      executeSelected,
      execute,
      open,
      close
    };
  }
});
</script>

<style scoped>
.command-palette-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(4px);
  z-index: 9999;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding-top: 100px;
  animation: fadeIn 0.2s ease;
}

.command-palette {
  background: white;
  border-radius: 12px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
  width: 90%;
  max-width: 600px;
  max-height: 500px;
  display: flex;
  flex-direction: column;
  animation: slideDown 0.2s ease;
}

.command-input-wrapper {
  display: flex;
  align-items: center;
  padding: 16px;
  border-bottom: 1px solid #e5e7eb;
  position: relative;
}

.command-input-wrapper i {
  color: #6b7280;
  margin-right: 12px;
  font-size: 18px;
}

.command-input {
  flex: 1;
  border: none;
  outline: none;
  font-size: 16px;
  background: transparent;
}

.escape-hint {
  position: absolute;
  right: 16px;
  top: 50%;
  transform: translateY(-50%);
  font-size: 11px;
  padding: 2px 6px;
  background: #f3f4f6;
  border-radius: 4px;
  color: #6b7280;
}

.command-results {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.no-results {
  padding: 32px;
  text-align: center;
  color: #6b7280;
}

.command-category {
  font-size: 12px;
  font-weight: 600;
  color: #6b7280;
  text-transform: uppercase;
  padding: 8px 12px 4px;
  margin-top: 8px;
}

.command-category:first-child {
  margin-top: 0;
}

.command-item {
  display: flex;
  align-items: center;
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.command-item:hover,
.command-item.selected {
  background: #f3f4f6;
}

.command-item.selected {
  background: #e5e7eb;
}

.command-icon {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f9fafb;
  border-radius: 6px;
  margin-right: 12px;
  color: #4b5563;
}

.command-item.selected .command-icon {
  background: #ddd6fe;
  color: #7c3aed;
}

.command-info {
  flex: 1;
}

.command-title {
  font-size: 14px;
  font-weight: 500;
  color: #111827;
}

.command-description {
  font-size: 12px;
  color: #6b7280;
  margin-top: 2px;
}

.command-shortcut {
  display: flex;
  gap: 4px;
}

.command-shortcut kbd {
  font-size: 11px;
  padding: 2px 6px;
  background: #f3f4f6;
  border: 1px solid #e5e7eb;
  border-radius: 4px;
  color: #4b5563;
  font-family: monospace;
}

/* Dark mode support */
body.dark-mode .command-palette {
  background: #1f2937;
  color: #f3f4f6;
}

body.dark-mode .command-input-wrapper {
  border-bottom-color: #374151;
}

body.dark-mode .command-input {
  color: #f3f4f6;
}

body.dark-mode .command-item:hover,
body.dark-mode .command-item.selected {
  background: #374151;
}

body.dark-mode .command-title {
  color: #f3f4f6;
}

body.dark-mode .command-icon {
  background: #374151;
  color: #9ca3af;
}

body.dark-mode .command-item.selected .command-icon {
  background: #7c3aed;
  color: white;
}

/* Animations */
@keyframes fadeIn {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}

@keyframes slideDown {
  from {
    transform: translateY(-20px);
    opacity: 0;
  }
  to {
    transform: translateY(0);
    opacity: 1;
  }
}
</style>
