<template>
  <div class="view">
    <div class="view-header">
      <h1 class="view-title">Settings</h1>
    </div>

    <div v-if="loading" class="text-center" style="padding: 2rem 0;">
      <div class="spinner" role="status" aria-label="Loading"></div>
    </div>

    <div v-else class="grid">
      <!-- Application Settings Section -->
      <div class="card" :style="{ backgroundColor: styleSettings.cardBg, color: styleSettings.textPrimary, borderColor: styleSettings.cardBorder }">
        <div style="padding: 1rem;">
          <h3>Application Settings</h3>

          <div style="margin-bottom: 1rem;">
            <label class="form-label">Application Theme</label>
            <div style="display: flex; gap: 0.5rem;">
              <label style="display: flex; align-items: center; gap: 0.5rem; padding: 0.5rem 1rem; border: 1px solid var(--color-border); border-radius: 4px; cursor: pointer;">
                <input
                  type="radio"
                  name="theme"
                  value="light"
                  v-model="currentTheme"
                  @change="changeTheme"
                  style="margin: 0;"
                />
                <i class="bi bi-sun-fill"></i>Light Mode
              </label>

              <label style="display: flex; align-items: center; gap: 0.5rem; padding: 0.5rem 1rem; border: 1px solid var(--color-border); border-radius: 4px; cursor: pointer;">
                <input
                  type="radio"
                  name="theme"
                  value="dark"
                  v-model="currentTheme"
                  @change="changeTheme"
                  style="margin: 0;"
                />
                <i class="bi bi-moon-fill"></i>Dark Mode
              </label>
            </div>
            <small style="color: var(--color-text); opacity: 0.7; display: block; margin-top: 0.5rem;">Choose your preferred application theme</small>
          </div>

          <div v-if="filteredSettings.length > 0">
            <form @submit.prevent="saveSettings">
              <div v-for="setting in filteredSettings" :key="setting.id" style="margin-bottom: 1rem;">
                <label :for="`setting-${setting.id}`" class="form-label">
                  {{ setting.description || setting.key }}
                </label>
                <input
                  :id="`setting-${setting.id}`"
                  :name="`setting-${setting.id}`"
                  v-model="setting.value"
                  type="text"
                  class="input"
                  :placeholder="setting.key"
                />
                <small style="color: var(--text-primary); opacity: 0.7; display: block; margin-top: 0.25rem;">Key: {{ setting.key }}</small>
              </div>
              <button type="submit" class="button button-primary" :disabled="saving">
                {{ saving ? 'Saving...' : 'Save Settings' }}
              </button>
            </form>
          </div>
          <div v-else>
            <p>No settings available</p>
          </div>
        </div>
      </div>

      <!-- Light Theme Style Customization Section -->
      <div class="card" :style="{ backgroundColor: styleSettings.cardBg, color: styleSettings.textPrimary, borderColor: styleSettings.cardBorder }">
        <div style="padding: 1rem;">
          <h3>Light Theme Style Customization</h3>

          <form @submit.prevent="saveLightStyleSettings">
            <!-- Background Colors -->
            <div style="margin-bottom: 1.5rem;">
              <h4 style="margin-bottom: 0.75rem; color: var(--color-text);">Background Colors</h4>

              <!-- Body Background -->
              <div style="margin-bottom: 1rem;">
                <label for="light-body-bg-color" class="form-label">Body Background Color</label>
                <div style="display: flex; align-items: center; gap: 0.5rem;">
                  <input
                    id="light-body-bg-color"
                    v-model="lightStyleSettings.bodyBg"
                    type="color"
                    class="form-control"
                    style="width: 60px; padding: 0; border: none;"
                  />
                  <input
                    id="light-body-bg-text"
                    v-model="lightStyleSettings.bodyBg"
                    type="text"
                    class="input"
                    placeholder="#ffffff"
                    style="max-width: 150px;"
                  />
                </div>
              </div>

              <!-- Content Background -->
              <div style="margin-bottom: 1rem;">
                <label for="light-content-bg-color" class="form-label">Content Background Color</label>
                <div style="display: flex; align-items: center; gap: 0.5rem;">
                  <input
                    id="light-content-bg-color"
                    v-model="lightStyleSettings.contentBg"
                    type="color"
                    class="form-control"
                    style="width: 60px; padding: 0; border: none;"
                  />
                  <input
                    id="light-content-bg-text"
                    v-model="lightStyleSettings.contentBg"
                    type="text"
                    class="input"
                    placeholder="#ffffff"
                    style="max-width: 150px;"
                  />
                </div>
              </div>
            </div>

            <!-- Button Colors -->
            <div style="margin-bottom: 1.5rem;">
              <h4 style="margin-bottom: 0.75rem; color: var(--color-text);">Button Colors</h4>

              <!-- Primary Button Color -->
              <div style="margin-bottom: 1rem;">
                <label for="light-button-primary-color" class="form-label">Primary Button Color</label>
                <div style="display: flex; align-items: center; gap: 0.5rem;">
                  <input
                    id="light-button-primary-color"
                    v-model="lightStyleSettings.buttonPrimaryBg"
                    type="color"
                    class="form-control"
                    style="width: 60px; padding: 0; border: none;"
                  />
                  <input
                    id="light-button-primary-text"
                    v-model="lightStyleSettings.buttonPrimaryBg"
                    type="text"
                    class="input"
                    placeholder="#007bff"
                    style="max-width: 150px;"
                  />
                </div>
              </div>

              <!-- Secondary Button Color -->
              <div style="margin-bottom: 1rem;">
                <label for="light-button-secondary-color" class="form-label">Secondary Button Color</label>
                <div style="display: flex; align-items: center; gap: 0.5rem;">
                  <input
                    id="light-button-secondary-color"
                    v-model="lightStyleSettings.buttonSecondaryBg"
                    type="color"
                    class="form-control"
                    style="width: 60px; padding: 0; border: none;"
                  />
                  <input
                    id="light-button-secondary-text"
                    v-model="lightStyleSettings.buttonSecondaryBg"
                    type="text"
                    class="input"
                    placeholder="#6c757d"
                    style="max-width: 150px;"
                  />
                </div>
              </div>

              <!-- Danger Button Color -->
              <div style="margin-bottom: 1rem;">
                <label for="light-button-danger-color" class="form-label">Danger Button Color</label>
                <div style="display: flex; align-items: center; gap: 0.5rem;">
                  <input
                    id="light-button-danger-color"
                    v-model="lightStyleSettings.buttonDangerBg"
                    type="color"
                    class="form-control"
                    style="width: 60px; padding: 0; border: none;"
                  />
                  <input
                    id="light-button-danger-text"
                    v-model="lightStyleSettings.buttonDangerBg"
                    type="text"
                    class="input"
                    placeholder="#dc3545"
                    style="max-width: 150px;"
                  />
                </div>
              </div>
            </div>

            <!-- Card and Component Colors -->
            <div style="margin-bottom: 1.5rem;">
              <h4 style="margin-bottom: 0.75rem; color: var(--color-text);">Card & Component Colors</h4>

              <!-- Card Background Color -->
              <div style="margin-bottom: 1rem;">
                <label for="light-card-bg-color" class="form-label">Card Background Color</label>
                <div style="display: flex; align-items: center; gap: 0.5rem;">
                  <input
                    id="light-card-bg-color"
                    v-model="lightStyleSettings.cardBg"
                    type="color"
                    class="form-control"
                    style="width: 60px; padding: 0; border: none;"
                  />
                  <input
                    id="light-card-bg-text"
                    v-model="lightStyleSettings.cardBg"
                    type="text"
                    class="input"
                    placeholder="#ffffff"
                    style="max-width: 150px;"
                  />
                </div>
              </div>

              <!-- Card Border Color -->
              <div style="margin-bottom: 1rem;">
                <label for="light-card-border-color" class="form-label">Card Border Color</label>
                <div style="display: flex; align-items: center; gap: 0.5rem;">
                  <input
                    id="light-card-border-color"
                    v-model="lightStyleSettings.cardBorder"
                    type="color"
                    class="form-control"
                    style="width: 60px; padding: 0; border: none;"
                  />
                  <input
                    id="light-card-border-text"
                    v-model="lightStyleSettings.cardBorder"
                    type="text"
                    class="input"
                    placeholder="#e3e3e3"
                    style="max-width: 150px;"
                  />
                </div>
              </div>

              <!-- Panel Background Color -->
              <div style="margin-bottom: 1rem;">
                <label for="light-panel-bg-color" class="form-label">Panel Background Color</label>
                <div style="display: flex; align-items: center; gap: 0.5rem;">
                  <input
                    id="light-panel-bg-color"
                    v-model="lightStyleSettings.panelBg"
                    type="color"
                    class="form-control"
                    style="width: 60px; padding: 0; border: none;"
                  />
                  <input
                    id="light-panel-bg-text"
                    v-model="lightStyleSettings.panelBg"
                    type="text"
                    class="input"
                    placeholder="#ffffff"
                    style="max-width: 150px;"
                  />
                </div>
              </div>
            </div>

            <!-- Text Colors -->
            <div style="margin-bottom: 1.5rem;">
              <h4 style="margin-bottom: 0.75rem; color: var(--color-text);">Text Colors</h4>

              <!-- Primary Text Color -->
              <div style="margin-bottom: 1rem;">
                <label for="light-text-primary-color" class="form-label">Primary Text Color</label>
                <div style="display: flex; align-items: center; gap: 0.5rem;">
                  <input
                    id="light-text-primary-color"
                    v-model="lightStyleSettings.textPrimary"
                    type="color"
                    class="form-control"
                    style="width: 60px; padding: 0; border: none;"
                  />
                  <input
                    id="light-text-primary-text"
                    v-model="lightStyleSettings.textPrimary"
                    type="text"
                    class="input"
                    placeholder="#222222"
                    style="max-width: 150px;"
                  />
                </div>
              </div>

              <!-- Secondary Text Color -->
              <div style="margin-bottom: 1rem;">
                <label for="light-text-secondary-color" class="form-label">Secondary Text Color</label>
                <div style="display: flex; align-items: center; gap: 0.5rem;">
                  <input
                    id="light-text-secondary-color"
                    v-model="lightStyleSettings.textSecondary"
                    type="color"
                    class="form-control"
                    style="width: 60px; padding: 0; border: none;"
                  />
                  <input
                    id="light-text-secondary-text"
                    v-model="lightStyleSettings.textSecondary"
                    type="text"
                    class="input"
                    placeholder="#666666"
                    style="max-width: 150px;"
                  />
                </div>
              </div>

              <!-- Muted Text Color -->
              <div style="margin-bottom: 1rem;">
                <label for="light-text-muted-color" class="form-label">Muted Text Color</label>
                <div style="display: flex; align-items: center; gap: 0.5rem;">
                  <input
                    id="light-text-muted-color"
                    v-model="lightStyleSettings.textMuted"
                    type="color"
                    class="form-control"
                    style="width: 60px; padding: 0; border: none;"
                  />
                  <input
                    id="light-text-muted-text"
                    v-model="lightStyleSettings.textMuted"
                    type="text"
                    class="input"
                    placeholder="#999999"
                    style="max-width: 150px;"
                  />
                </div>
              </div>
            </div>

            <!-- Border Radius -->
            <div style="margin-bottom: 1.5rem;">
              <h4 style="margin-bottom: 0.75rem; color: var(--color-text);">Border Radius</h4>

              <div style="margin-bottom: 1rem;">
                <label for="light-border-radius-sm" class="form-label">Border Radius (Small)</label>
                <input
                  id="light-border-radius-sm"
                  v-model="lightStyleSettings.borderRadiusSm"
                  type="range"
                  min="0"
                  max="20"
                  step="1"
                  class="input"
                  style="max-width: 200px;"
                />
                <span style="margin-left: 0.5rem; color: var(--text-primary);">{{ lightStyleSettings.borderRadiusSm }}px</span>
              </div>

              <div style="margin-bottom: 1rem;">
                <label for="light-border-radius-md" class="form-label">Border Radius (Medium)</label>
                <input
                  id="light-border-radius-md"
                  v-model="lightStyleSettings.borderRadiusMd"
                  type="range"
                  min="0"
                  max="30"
                  step="1"
                  class="input"
                  style="max-width: 200px;"
                />
                <span style="margin-left: 0.5rem; color: var(--text-primary);">{{ lightStyleSettings.borderRadiusMd }}px</span>
              </div>

              <div style="margin-bottom: 1rem;">
                <label for="light-border-radius-lg" class="form-label">Border Radius (Large)</label>
                <input
                  id="light-border-radius-lg"
                  v-model="lightStyleSettings.borderRadiusLg"
                  type="range"
                  min="0"
                  max="50"
                  step="1"
                  class="input"
                  style="max-width: 200px;"
                />
                <span style="margin-left: 0.5rem; color: var(--text-primary);">{{ lightStyleSettings.borderRadiusLg }}px</span>
              </div>
            </div>

            <!-- Preview -->
            <div style="margin-bottom: 1rem;">
              <label class="form-label">Preview</label>
              <div
                style="padding: 1rem; border-radius: 8px; border: 1px solid var(--color-border);"
                :style="{
                  backgroundColor: lightStyleSettings.cardBg,
                  borderColor: lightStyleSettings.cardBorder,
                  borderRadius: lightStyleSettings.borderRadiusMd + 'px'
                }"
              >
                <h5 style="margin: 0 0 1rem 0; color: var(--color-text);">Sample Card</h5>
                <p style="margin: 0 0 1rem 0; color: var(--color-text); opacity: 0.8;">This is how your styled components will look.</p>
                <button
                  style="margin-right: 0.5rem; padding: 0.5rem 1rem; border: none; cursor: pointer;"
                  :style="{
                    backgroundColor: lightStyleSettings.buttonPrimaryBg,
                    color: '#ffffff',
                    borderRadius: lightStyleSettings.borderRadiusSm + 'px'
                  }"
                >
                  Primary Button
                </button>
                <button
                  style="margin-right: 0.5rem; padding: 0.5rem 1rem; border: none; cursor: pointer;"
                  :style="{
                    backgroundColor: lightStyleSettings.buttonSecondaryBg,
                    color: '#ffffff',
                    borderRadius: lightStyleSettings.borderRadiusSm + 'px'
                  }"
                >
                  Secondary Button
                </button>
                <button
                  style="padding: 0.5rem 1rem; border: none; cursor: pointer;"
                  :style="{
                    backgroundColor: lightStyleSettings.buttonDangerBg,
                    color: '#ffffff',
                    borderRadius: lightStyleSettings.borderRadiusSm + 'px'
                  }"
                >
                  Danger Button
                </button>
              </div>
            </div>

            <button type="submit" class="button button-primary" :disabled="savingLightStyle">
              {{ savingLightStyle ? 'Saving...' : 'Save Light Style Settings' }}
            </button>
          </form>
        </div>
      </div>

      <!-- Dark Theme Style Customization Section -->
      <div class="card" :style="{ backgroundColor: styleSettings.cardBg, color: styleSettings.textPrimary, borderColor: styleSettings.cardBorder }">
        <div style="padding: 1rem;">
          <h3>Dark Theme Style Customization</h3>

          <form @submit.prevent="saveDarkStyleSettings">
            <!-- Background Colors -->
            <div style="margin-bottom: 1.5rem;">
              <h4 style="margin-bottom: 0.75rem; color: var(--color-text);">Background Colors</h4>

              <!-- Body Background -->
              <div style="margin-bottom: 1rem;">
                <label for="dark-body-bg-color" class="form-label">Body Background Color</label>
                <div style="display: flex; align-items: center; gap: 0.5rem;">
                  <input
                    id="dark-body-bg-color"
                    v-model="darkStyleSettings.bodyBg"
                    type="color"
                    class="form-control"
                    style="width: 60px; padding: 0; border: none;"
                  />
                  <input
                    id="dark-body-bg-text"
                    v-model="darkStyleSettings.bodyBg"
                    type="text"
                    class="input"
                    placeholder="#1f2937"
                    style="max-width: 150px;"
                  />
                </div>
              </div>

              <!-- Content Background -->
              <div style="margin-bottom: 1rem;">
                <label for="dark-content-bg-color" class="form-label">Content Background Color</label>
                <div style="display: flex; align-items: center; gap: 0.5rem;">
                  <input
                    id="dark-content-bg-color"
                    v-model="darkStyleSettings.contentBg"
                    type="color"
                    class="form-control"
                    style="width: 60px; padding: 0; border: none;"
                  />
                  <input
                    id="dark-content-bg-text"
                    v-model="darkStyleSettings.contentBg"
                    type="text"
                    class="input"
                    placeholder="#1f2937"
                    style="max-width: 150px;"
                  />
                </div>
              </div>
            </div>

            <!-- Button Colors -->
            <div style="margin-bottom: 1.5rem;">
              <h4 style="margin-bottom: 0.75rem; color: var(--color-text);">Button Colors</h4>

              <!-- Primary Button Color -->
              <div style="margin-bottom: 1rem;">
                <label for="dark-button-primary-color" class="form-label">Primary Button Color</label>
                <div style="display: flex; align-items: center; gap: 0.5rem;">
                  <input
                    id="dark-button-primary-color"
                    v-model="darkStyleSettings.buttonPrimaryBg"
                    type="color"
                    class="form-control"
                    style="width: 60px; padding: 0; border: none;"
                  />
                  <input
                    id="dark-button-primary-text"
                    v-model="darkStyleSettings.buttonPrimaryBg"
                    type="text"
                    class="input"
                    placeholder="#3b82f6"
                    style="max-width: 150px;"
                  />
                </div>
              </div>

              <!-- Secondary Button Color -->
              <div style="margin-bottom: 1rem;">
                <label for="dark-button-secondary-color" class="form-label">Secondary Button Color</label>
                <div style="display: flex; align-items: center; gap: 0.5rem;">
                  <input
                    id="dark-button-secondary-color"
                    v-model="darkStyleSettings.buttonSecondaryBg"
                    type="color"
                    class="form-control"
                    style="width: 60px; padding: 0; border: none;"
                  />
                  <input
                    id="dark-button-secondary-text"
                    v-model="darkStyleSettings.buttonSecondaryBg"
                    type="text"
                    class="input"
                    placeholder="#6b7280"
                    style="max-width: 150px;"
                  />
                </div>
              </div>

              <!-- Danger Button Color -->
              <div style="margin-bottom: 1rem;">
                <label for="dark-button-danger-color" class="form-label">Danger Button Color</label>
                <div style="display: flex; align-items: center; gap: 0.5rem;">
                  <input
                    id="dark-button-danger-color"
                    v-model="darkStyleSettings.buttonDangerBg"
                    type="color"
                    class="form-control"
                    style="width: 60px; padding: 0; border: none;"
                  />
                  <input
                    id="dark-button-danger-text"
                    v-model="darkStyleSettings.buttonDangerBg"
                    type="text"
                    class="input"
                    placeholder="#ef4444"
                    style="max-width: 150px;"
                  />
                </div>
              </div>
            </div>

            <!-- Card and Component Colors -->
            <div style="margin-bottom: 1.5rem;">
              <h4 style="margin-bottom: 0.75rem; color: var(--color-text);">Card & Component Colors</h4>

              <!-- Card Background Color -->
              <div style="margin-bottom: 1rem;">
                <label for="dark-card-bg-color" class="form-label">Card Background Color</label>
                <div style="display: flex; align-items: center; gap: 0.5rem;">
                  <input
                    id="dark-card-bg-color"
                    v-model="darkStyleSettings.cardBg"
                    type="color"
                    class="form-control"
                    style="width: 60px; padding: 0; border: none;"
                  />
                  <input
                    id="dark-card-bg-text"
                    v-model="darkStyleSettings.cardBg"
                    type="text"
                    class="input"
                    placeholder="#374151"
                    style="max-width: 150px;"
                  />
                </div>
              </div>

              <!-- Card Border Color -->
              <div style="margin-bottom: 1rem;">
                <label for="dark-card-border-color" class="form-label">Card Border Color</label>
                <div style="display: flex; align-items: center; gap: 0.5rem;">
                  <input
                    id="dark-card-border-color"
                    v-model="darkStyleSettings.cardBorder"
                    type="color"
                    class="form-control"
                    style="width: 60px; padding: 0; border: none;"
                  />
                  <input
                    id="dark-card-border-text"
                    v-model="darkStyleSettings.cardBorder"
                    type="text"
                    class="input"
                    placeholder="#4b5563"
                    style="max-width: 150px;"
                  />
                </div>
              </div>

              <!-- Panel Background Color -->
              <div style="margin-bottom: 1rem;">
                <label for="dark-panel-bg-color" class="form-label">Panel Background Color</label>
                <div style="display: flex; align-items: center; gap: 0.5rem;">
                  <input
                    id="dark-panel-bg-color"
                    v-model="darkStyleSettings.panelBg"
                    type="color"
                    class="form-control"
                    style="width: 60px; padding: 0; border: none;"
                  />
                  <input
                    id="dark-panel-bg-text"
                    v-model="darkStyleSettings.panelBg"
                    type="text"
                    class="input"
                    placeholder="#374151"
                    style="max-width: 150px;"
                  />
                </div>
              </div>
            </div>

            <!-- Text Colors -->
            <div style="margin-bottom: 1.5rem;">
              <h4 style="margin-bottom: 0.75rem; color: var(--color-text);">Text Colors</h4>

              <!-- Primary Text Color -->
              <div style="margin-bottom: 1rem;">
                <label for="dark-text-primary-color" class="form-label">Primary Text Color</label>
                <div style="display: flex; align-items: center; gap: 0.5rem;">
                  <input
                    id="dark-text-primary-color"
                    v-model="darkStyleSettings.textPrimary"
                    type="color"
                    class="form-control"
                    style="width: 60px; padding: 0; border: none;"
                  />
                  <input
                    id="dark-text-primary-text"
                    v-model="darkStyleSettings.textPrimary"
                    type="text"
                    class="input"
                    placeholder="#e5e7eb"
                    style="max-width: 150px;"
                  />
                </div>
              </div>

              <!-- Secondary Text Color -->
              <div style="margin-bottom: 1rem;">
                <label for="dark-text-secondary-color" class="form-label">Secondary Text Color</label>
                <div style="display: flex; align-items: center; gap: 0.5rem;">
                  <input
                    id="dark-text-secondary-color"
                    v-model="darkStyleSettings.textSecondary"
                    type="color"
                    class="form-control"
                    style="width: 60px; padding: 0; border: none;"
                  />
                  <input
                    id="dark-text-secondary-text"
                    v-model="darkStyleSettings.textSecondary"
                    type="text"
                    class="input"
                    placeholder="#9ca3af"
                    style="max-width: 150px;"
                  />
                </div>
              </div>

              <!-- Muted Text Color -->
              <div style="margin-bottom: 1rem;">
                <label for="dark-text-muted-color" class="form-label">Muted Text Color</label>
                <div style="display: flex; align-items: center; gap: 0.5rem;">
                  <input
                    id="dark-text-muted-color"
                    v-model="darkStyleSettings.textMuted"
                    type="color"
                    class="form-control"
                    style="width: 60px; padding: 0; border: none;"
                  />
                  <input
                    id="dark-text-muted-text"
                    v-model="darkStyleSettings.textMuted"
                    type="text"
                    class="input"
                    placeholder="#6b7280"
                    style="max-width: 150px;"
                  />
                </div>
              </div>
            </div>

            <!-- Border Radius -->
            <div style="margin-bottom: 1.5rem;">
              <h4 style="margin-bottom: 0.75rem; color: var(--color-text);">Border Radius</h4>

              <div style="margin-bottom: 1rem;">
                <label for="dark-border-radius-sm" class="form-label">Border Radius (Small)</label>
                <input
                  id="dark-border-radius-sm"
                  v-model="darkStyleSettings.borderRadiusSm"
                  type="range"
                  min="0"
                  max="20"
                  step="1"
                  class="input"
                  style="max-width: 200px;"
                />
                <span style="margin-left: 0.5rem; color: var(--text-primary);">{{ darkStyleSettings.borderRadiusSm }}px</span>
              </div>

              <div style="margin-bottom: 1rem;">
                <label for="dark-border-radius-md" class="form-label">Border Radius (Medium)</label>
                <input
                  id="dark-border-radius-md"
                  v-model="darkStyleSettings.borderRadiusMd"
                  type="range"
                  min="0"
                  max="30"
                  step="1"
                  class="input"
                  style="max-width: 200px;"
                />
                <span style="margin-left: 0.5rem; color: var(--text-primary);">{{ darkStyleSettings.borderRadiusMd }}px</span>
              </div>

              <div style="margin-bottom: 1rem;">
                <label for="dark-border-radius-lg" class="form-label">Border Radius (Large)</label>
                <input
                  id="dark-border-radius-lg"
                  v-model="darkStyleSettings.borderRadiusLg"
                  type="range"
                  min="0"
                  max="50"
                  step="1"
                  class="input"
                  style="max-width: 200px;"
                />
                <span style="margin-left: 0.5rem; color: var(--text-primary);">{{ darkStyleSettings.borderRadiusLg }}px</span>
              </div>
            </div>

            <!-- Preview -->
            <div style="margin-bottom: 1rem;">
              <label class="form-label">Preview</label>
              <div
                style="padding: 1rem; border-radius: 8px; border: 1px solid var(--color-border);"
                :style="{
                  backgroundColor: darkStyleSettings.cardBg,
                  borderColor: darkStyleSettings.cardBorder,
                  borderRadius: darkStyleSettings.borderRadiusMd + 'px'
                }"
              >
                <h5 style="margin: 0 0 1rem 0; color: var(--color-text);">Sample Card</h5>
                <p style="margin: 0 0 1rem 0; color: var(--color-text); opacity: 0.8;">This is how your styled components will look.</p>
                <button
                  style="margin-right: 0.5rem; padding: 0.5rem 1rem; border: none; cursor: pointer;"
                  :style="{
                    backgroundColor: darkStyleSettings.buttonPrimaryBg,
                    color: '#ffffff',
                    borderRadius: darkStyleSettings.borderRadiusSm + 'px'
                  }"
                >
                  Primary Button
                </button>
                <button
                  style="margin-right: 0.5rem; padding: 0.5rem 1rem; border: none; cursor: pointer;"
                  :style="{
                    backgroundColor: darkStyleSettings.buttonSecondaryBg,
                    color: '#ffffff',
                    borderRadius: darkStyleSettings.borderRadiusSm + 'px'
                  }"
                >
                  Secondary Button
                </button>
                <button
                  style="padding: 0.5rem 1rem; border: none; cursor: pointer;"
                  :style="{
                    backgroundColor: darkStyleSettings.buttonDangerBg,
                    color: '#ffffff',
                    borderRadius: darkStyleSettings.borderRadiusSm + 'px'
                  }"
                >
                  Danger Button
                </button>
              </div>
            </div>

            <button type="submit" class="button button-primary" :disabled="savingDarkStyle">
              {{ savingDarkStyle ? 'Saving...' : 'Save Dark Style Settings' }}
            </button>
          </form>
        </div>
      </div>

      <!-- Header Customization Section -->
      <div class="card" :style="{ backgroundColor: styleSettings.cardBg, color: styleSettings.textPrimary, borderColor: styleSettings.cardBorder }">
        <div style="padding: 1rem;">
          <h3>Header Customization</h3>

          <form @submit.prevent="saveHeaderSettings">
            <!-- Site Name -->
            <div style="margin-bottom: 1rem;">
              <label for="site-name" class="form-label">Site Name</label>
              <input
                id="site-name"
                v-model="headerSettings.siteName"
                type="text"
                class="input"
                placeholder="Enter site name"
              />
            </div>

            <!-- Header Message -->
            <div style="margin-bottom: 1rem;">
              <label for="header-message" class="form-label">Header Message</label>
              <input
                id="header-message"
                v-model="headerSettings.headerMessage"
                type="text"
                class="input"
                placeholder="Welcome message or tagline"
              />
            </div>

            <!-- Logo Upload -->
            <div style="margin-bottom: 1rem;">
              <label class="form-label">Logo</label>
              <div style="display: flex; align-items: center; gap: 1rem;">
                <div v-if="headerSettings.logoUrl">
                  <img :src="headerSettings.logoUrl" alt="Logo" style="max-height: 60px; max-width: 200px;">
                  <button
                    type="button"
                    class="button button-danger button-sm"
                    style="margin-left: 0.5rem;"
                    @click="removeLogo"
                  >
                    Remove
                  </button>
                </div>
                <div>
                  <input
                    type="file"
                    class="input"
                    accept="image/*"
                    @change="handleLogoUpload"
                    ref="logoInput"
                  />
                  <small style="color: var(--color-text); opacity: 0.7; display: block; margin-top: 0.25rem;">Recommended: PNG or SVG, max 2MB</small>
                </div>
              </div>
            </div>

            <!-- Background Color -->
            <div style="margin-bottom: 1rem;">
              <label for="header-bg-color" class="form-label">Header Background Color</label>
              <div style="display: flex; align-items: center; gap: 0.5rem;">
                <input
                  id="header-bg-color"
                  v-model="headerSettings.backgroundColor"
                  type="color"
                  class="form-control"
                  style="width: 60px; padding: 0; border: none;"
                />
                <input
                  id="header-bg-text"
                  v-model="headerSettings.backgroundColor"
                  type="text"
                  class="input"
                  placeholder="#ffffff"
                  style="max-width: 150px;"
                />
              </div>
            </div>

            <!-- Text Color -->
            <div style="margin-bottom: 1rem;">
              <label for="header-text-color" class="form-label">Header Text Color</label>
              <div style="display: flex; align-items: center; gap: 0.5rem;">
                <input
                  id="header-text-color"
                  v-model="headerSettings.textColor"
                  type="color"
                  class="form-control"
                  style="width: 60px; padding: 0; border: none;"
                />
                <input
                  id="header-text-text"
                  v-model="headerSettings.textColor"
                  type="text"
                  class="input"
                  placeholder="#000000"
                  style="max-width: 150px;"
                />
              </div>
            </div>

            <!-- Preview -->
            <div style="margin-bottom: 1rem;">
              <label class="form-label">Preview</label>
              <div
                style="padding: 1rem; border-radius: 8px; text-align: center;"
                :style="{
                  backgroundColor: headerSettings.backgroundColor,
                  color: headerSettings.textColor
                }"
              >
                <img
                  v-if="headerSettings.logoUrl"
                  :src="headerSettings.logoUrl"
                  alt="Logo"
                  style="max-height: 60px; margin-bottom: 10px; display: block; margin-left: auto; margin-right: auto;"
                />
                <div style="font-weight: bold; font-size: 1.25rem;">{{ headerSettings.siteName || 'Site Name' }}</div>
                <div style="font-size: 0.875rem;">{{ headerSettings.headerMessage || 'Your message here' }}</div>
              </div>
            </div>

            <button type="submit" class="button button-primary" :disabled="savingHeader">
              {{ savingHeader ? 'Saving...' : 'Save Header Settings' }}
            </button>
          </form>
        </div>
      </div>


      <!-- Menu Section -->
      <div class="card" :style="{ backgroundColor: styleSettings.cardBg, color: styleSettings.textPrimary, borderColor: styleSettings.cardBorder }">
        <div style="padding: 1rem;">
          <h3>Menu Configuration</h3>

          <div v-if="menus.length > 0">
            <div style="margin-bottom: 1rem;">
              <label for="active-menu" class="form-label">Active Menu</label>
              <select id="active-menu" v-model="activeMenuId" @change="setActiveMenu" class="select">
                <option v-for="menu in menus" :key="menu.id" :value="menu.id">
                  {{ menu.name }}
                </option>
              </select>
            </div>

            <div v-if="activeMenu">
              <h4 style="margin-bottom: 1rem;">Menu Items (drag to reorder)</h4>
              <VueDraggable
                v-model="activeMenu.items"
                class="list-group"
                handle=".drag-handle"
                :animation="200"
                @end="onDragEnd"
              >
                <div v-for="(item, index) in activeMenu.items" :key="`${item.path}-${index}`" style="padding: 0.75rem; border: 1px solid var(--color-border); border-radius: 4px; margin-bottom: 0.5rem; background-color: var(--card-bg);">
                  <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div style="display: flex; align-items: center;">
                      <span class="drag-handle" style="cursor: move; margin-right: 0.5rem; font-size: 1.2rem; color: var(--color-text); opacity: 0.7;">
                        ☰
                      </span>
                      <div>
                        <strong>{{ item.label }}</strong>
                        <br>
                        <small style="color: var(--color-text); opacity: 0.7;">{{ item.path }}</small>
                      </div>
                    </div>
                    <div>
                      <button @click="editMenuItem(index)" class="button button-outline button-sm" style="margin-right: 0.25rem;">Edit</button>
                      <button @click="removeMenuItem(index)" class="button button-outline button-sm" style="--accent: var(--button-danger-bg); border-color: var(--button-danger-bg); color: var(--button-danger-bg);">Remove</button>
                    </div>
                  </div>
                </div>
              </VueDraggable>

              <div style="margin-top: 1rem;">
                <h4 style="margin-bottom: 0.5rem;">Add Menu Item</h4>
                <div style="display: grid; grid-template-columns: 1fr 1fr auto; gap: 0.5rem;">
                  <input id="new-menu-label" v-model="newItem.label" type="text" class="input" placeholder="Label">
                  <input id="new-menu-path" v-model="newItem.path" type="text" class="input" placeholder="Path">
                  <button @click="addMenuItem" class="button button-primary">Add</button>
                </div>
              </div>

              <button @click="saveMenu" class="button button-primary" style="margin-top: 1rem;" :disabled="savingMenu">
                {{ savingMenu ? 'Saving...' : 'Save Menu' }}
              </button>
            </div>
          </div>
          <div v-else>
            <p>No menus available</p>
          </div>
        </div>
      </div>
    </div>

    <div v-if="errorMessage" class="alert alert-danger" style="margin-top: 1rem;">{{ errorMessage }}</div>
    <div v-if="successMessage" class="alert alert-success" style="margin-top: 1rem;">{{ successMessage }}</div>
  </div>
</template>

<script lang="ts">
import { defineComponent, ref, onMounted, computed } from 'vue';
import { VueDraggable } from 'vue-draggable-plus';
import { useThemeStore } from '@/stores/theme';
import { useSettingsStore } from '@/stores/settings';
import http from '@/utils/http';

export default defineComponent({
  name: 'Settings',
  components: { VueDraggable },
  setup() {
    const themeStore = useThemeStore();
    const settingsStore = useSettingsStore();
    const settings = ref<any[]>([]);
    const menus = ref<any[]>([]);
    const loading = ref(false);
    const activeMenuId = ref<number | null>(null);
    const newItem = ref({ label: '', path: '', icon: '' });
    const errorMessage = ref('');
    const successMessage = ref('');
    const saving = ref(false);
    const savingMenu = ref(false);
    const savingHeader = ref(false);
    const savingStyle = ref(false);
    const savingLightStyle = ref(false);
    const savingDarkStyle = ref(false);
    const logoInput = ref<HTMLInputElement | null>(null);
    const currentTheme = ref<'light' | 'dark'>(themeStore.theme);

    // Use reactive settings from store
    const headerSettings = settingsStore.headerSettings;
    const styleSettings = settingsStore.styleSettings;
    const lightStyleSettings = settingsStore.lightStyleSettings;
    const darkStyleSettings = settingsStore.darkStyleSettings;

    const activeMenu = computed(() => {
      if (!activeMenuId.value) return null;
      return menus.value.find(m => m.id === activeMenuId.value);
    });

    // Filter out header-specific and theme-specific settings from general settings
    const filteredSettings = computed(() => {
      const excludedKeys = [
        'site_name', 'header_message', 'logo_url', 'header_bg_color', 'header_text_color',
        // Light theme settings
        'light_body_bg', 'light_content_bg', 'light_button_primary_bg', 'light_button_secondary_bg', 'light_button_danger_bg',
        'light_card_bg', 'light_card_border', 'light_panel_bg', 'light_text_primary', 'light_text_secondary', 'light_text_muted',
        'light_border_radius_sm', 'light_border_radius_md', 'light_border_radius_lg',
        // Dark theme settings
        'dark_body_bg', 'dark_content_bg', 'dark_button_primary_bg', 'dark_button_secondary_bg', 'dark_button_danger_bg',
        'dark_card_bg', 'dark_card_border', 'dark_panel_bg', 'dark_text_primary', 'dark_text_secondary', 'dark_text_muted',
        'dark_border_radius_sm', 'dark_border_radius_md', 'dark_border_radius_lg',
        // Old theme settings (deprecated)
        'theme', 'button_primary_bg', 'button_secondary_bg', 'card_bg', 'card_border', 'body_bg', 'content_bg',
        'button_danger_bg', 'panel_bg', 'text_primary', 'text_secondary', 'text_muted',
        'border_radius_sm', 'border_radius_md', 'border_radius_lg'
      ];
      return settings.value.filter(s => !excludedKeys.includes(s.key));
    });

    const fetchSettings = async () => {
      try {
        const response = await http.get('/settings/read');
        settings.value = response.data.items || [];

        // Load settings into the store
        await settingsStore.loadSettings();
      } catch (error) {
        console.error('Failed to fetch settings:', error);
        errorMessage.value = 'Failed to fetch settings.';
      }
    };

    const fetchMenus = async () => {
      try {
        const response = await http.get('/menu/read');
        menus.value = response.data.items || [];
        // Set active menu
        const active = menus.value.find(m => m.is_active);
        if (active) {
          activeMenuId.value = active.id;
        } else if (menus.value.length > 0) {
          activeMenuId.value = menus.value[0].id;
        }
      } catch (error) {
        console.error('Failed to fetch menus:', error);
        errorMessage.value = 'Failed to fetch menus.';
      }
    };

    const saveSettings = async () => {
      saving.value = true;
      errorMessage.value = '';
      successMessage.value = '';
      
      try {
        // Save each setting individually
        for (const setting of settings.value) {
          await http.put('/settings/update', {
            id: setting.id,
            key: setting.key,
            value: setting.value,
            description: setting.description
          });
        }
        successMessage.value = 'Settings saved successfully!';
        setTimeout(() => successMessage.value = '', 3000);
      } catch (error) {
        console.error('Failed to save settings:', error);
        errorMessage.value = 'Failed to save settings.';
      } finally {
        saving.value = false;
        // Notify other components (e.g., Menu) that settings have changed
        window.dispatchEvent(new Event('settings-updated'));
      }
    };

    const setActiveMenu = async () => {
      // Update all menus to set the active one
      for (const menu of menus.value) {
        menu.is_active = menu.id === activeMenuId.value;
      }
    };

    const addMenuItem = () => {
      if (!newItem.value.label || !newItem.value.path) return;
      if (!activeMenu.value) return;
      
      if (!activeMenu.value.items) {
        activeMenu.value.items = [];
      }
      
      activeMenu.value.items.push({
        label: newItem.value.label,
        path: newItem.value.path,
        icon: newItem.value.icon || ''
      });
      
      newItem.value = { label: '', path: '', icon: '' };
    };

    const editMenuItem = (index: number) => {
      if (!activeMenu.value) return;
      const item = activeMenu.value.items[index];
      const newLabel = prompt('Enter new label:', item.label);
      const newPath = prompt('Enter new path:', item.path);
      
      if (newLabel && newPath) {
        item.label = newLabel;
        item.path = newPath;
      }
    };

    const removeMenuItem = (index: number) => {
      if (!activeMenu.value) return;
      if (confirm('Remove this menu item?')) {
        activeMenu.value.items.splice(index, 1);
      }
    };
    
    const onDragEnd = () => {
      // Menu items have been reordered, no additional action needed
      // The v-model binding automatically updates the array
      console.log('Menu items reordered');
    };

    const saveMenu = async () => {
      if (!activeMenu.value) return;
      
      savingMenu.value = true;
      errorMessage.value = '';
      successMessage.value = '';
      
      try {
        await http.put('/menu/update', {
          id: activeMenu.value.id,
          name: activeMenu.value.name,
          items: activeMenu.value.items,
          is_active: activeMenu.value.is_active
        });
        successMessage.value = 'Menu saved successfully!';
        setTimeout(() => successMessage.value = '', 3000);
      } catch (error) {
        console.error('Failed to save menu:', error);
        errorMessage.value = 'Failed to save menu.';
      } finally {
        savingMenu.value = false;
      }
    };

    const handleLogoUpload = async (event: Event) => {
      const target = event.target as HTMLInputElement;
      const file = target.files?.[0];
      
      if (!file) return;
      
      // Check file size (2MB limit)
      if (file.size > 2 * 1024 * 1024) {
        errorMessage.value = 'Logo file size must be less than 2MB';
        return;
      }
      
      // Convert to base64
      const reader = new FileReader();
      reader.onload = (e) => {
        headerSettings.logoUrl = e.target?.result as string;
      };
      reader.readAsDataURL(file);
    };
    
    const removeLogo = () => {
      headerSettings.logoUrl = '';
      if (logoInput.value) {
        logoInput.value.value = '';
      }
    };
    
    const saveHeaderSettings = async () => {
      savingHeader.value = true;
      errorMessage.value = '';
      successMessage.value = '';

      try {
        await settingsStore.saveHeaderSettings();
        successMessage.value = 'Header settings saved successfully!';
        setTimeout(() => successMessage.value = '', 3000);

        // Refresh settings
        await fetchSettings();
      } catch (error) {
        console.error('Failed to save header settings:', error);
        errorMessage.value = 'Failed to save header settings.';
      } finally {
        savingHeader.value = false;
      }
    };

    const saveStyleSettings = async () => {
      savingStyle.value = true;
      errorMessage.value = '';
      successMessage.value = '';

      try {
        await settingsStore.saveStyleSettings();
        successMessage.value = 'Style settings saved successfully!';
        setTimeout(() => successMessage.value = '', 3000);

        // Refresh settings
        await fetchSettings();
      } catch (error) {
        console.error('Failed to save style settings:', error);
        errorMessage.value = 'Failed to save style settings.';
      } finally {
        savingStyle.value = false;
      }
    };

    const saveLightStyleSettings = async () => {
      savingLightStyle.value = true;
      errorMessage.value = '';
      successMessage.value = '';

      try {
        await settingsStore.saveLightStyleSettings();
        successMessage.value = 'Light style settings saved successfully!';
        setTimeout(() => successMessage.value = '', 3000);

        // Refresh settings and reload from backend
        await fetchSettings();
        await settingsStore.loadSettings();

        // Apply CSS variables only if light theme is active
        if (themeStore.theme === 'light') {
          settingsStore.updateCSSVariables();
        }
      } catch (error) {
        console.error('Failed to save light style settings:', error);
        errorMessage.value = 'Failed to save light style settings.';
      } finally {
        savingLightStyle.value = false;
      }
    };

    const saveDarkStyleSettings = async () => {
      savingDarkStyle.value = true;
      errorMessage.value = '';
      successMessage.value = '';

      try {
        await settingsStore.saveDarkStyleSettings();
        successMessage.value = 'Dark style settings saved successfully!';
        setTimeout(() => successMessage.value = '', 3000);

        // Refresh settings and reload from backend
        await fetchSettings();
        await settingsStore.loadSettings();

        // Apply CSS variables only if dark theme is active
        if (themeStore.theme === 'dark') {
          settingsStore.updateCSSVariables();
        }
      } catch (error) {
        console.error('Failed to save dark style settings:', error);
        errorMessage.value = 'Failed to save dark style settings.';
      } finally {
        savingDarkStyle.value = false;
      }
    };


    const changeTheme = () => {
      themeStore.setTheme(currentTheme.value);
    };

    onMounted(async () => {
      loading.value = true;
      await Promise.all([fetchSettings(), fetchMenus()]);
      loading.value = false;

      // Apply initial CSS variables
      settingsStore.updateCSSVariables();
    });

    return {
      settings,
      filteredSettings,
      menus,
      loading,
      activeMenuId,
      activeMenu,
      newItem,
      errorMessage,
      successMessage,
      saving,
      savingMenu,
      savingHeader,
      savingStyle,
      savingLightStyle,
      savingDarkStyle,
      headerSettings,
      styleSettings,
      lightStyleSettings,
      darkStyleSettings,
      logoInput,
      currentTheme,
      saveSettings,
      setActiveMenu,
      addMenuItem,
      editMenuItem,
      removeMenuItem,
      saveMenu,
      onDragEnd,
      handleLogoUpload,
      removeLogo,
      saveHeaderSettings,
      saveStyleSettings,
      saveLightStyleSettings,
      saveDarkStyleSettings,
      changeTheme
    };
  },
});
</script>

<style scoped>
/* Settings-specific styles if needed */
</style>
