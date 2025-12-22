<template>
  <div class="view">
    <div class="view-header">
      <h1 class="view-title">{{ t('extensions.aiBuilder.title', 'AI Extension Builder') }}</h1>
      <p class="muted">
        {{ t('extensions.aiBuilder.subtitle', 'Generate a relationship-aware extension ZIP and install it.') }}
      </p>
    </div>

    <div class="card" :style="cardStyle">
      <div class="card-content">
        <div class="stepper">
          <button
            v-for="(s, idx) in steps"
            :key="s.key"
            class="step"
            :class="{ active: idx === currentStep, done: isStepDone(idx) }"
            @click="goStep(idx)"
          >
            <span class="step-index">{{ idx + 1 }}</span>
            <span class="step-label">{{ s.label }}</span>
          </button>
        </div>

        <div class="row" style="margin-top: 0.75rem">
          <button class="button" :disabled="currentStep === 0" @click="prevStep">
            {{ t('extensions.aiBuilder.steps.back', 'Back') }}
          </button>
          <button class="button button-primary" :disabled="currentStep === steps.length - 1" @click="nextStep">
            {{ t('extensions.aiBuilder.steps.next', 'Next') }}
          </button>
        </div>
      </div>
    </div>

    <div class="card" :style="cardStyle">
      <div class="card-content">
        <h2>{{ t('extensions.aiBuilder.spec', 'Extension spec') }}</h2>

        <details v-show="currentStep === 0" open class="section">
          <summary class="section-title">
            {{ t('extensions.aiBuilder.sections.basic', 'Basic') }}
          </summary>

          <div class="grid">
            <div class="form-group">
              <label>{{ t('extensions.aiBuilder.name', 'Name') }}</label>
              <input v-model="spec.name" @input="touched.name = true" />
              <div class="hint muted">
                {{
                  t(
                    'extensions.aiBuilder.hints.name',
                    'Tip: Use PascalCase, e.g. StoreExtension or MyExtension.'
                  )
                }}
              </div>
            </div>

            <div class="form-group">
              <label>{{ t('extensions.aiBuilder.template', 'Template') }}</label>
              <select v-model="templateKey" :disabled="busy">
                <option value="simple">{{ t('extensions.aiBuilder.templates.simple', 'Simple route extension') }}</option>
                <option value="crud">{{ t('extensions.aiBuilder.templates.crud', 'CRUD (DB) extension') }}</option>
                <option value="crud_multilingual">{{ t('extensions.aiBuilder.templates.crudMultilingual', 'CRUD + multilingual content') }}</option>
                <option value="provider_embedder">{{ t('extensions.aiBuilder.templates.provider', 'Provider embedder extension') }}</option>
                <option value="consumer_embedder">{{ t('extensions.aiBuilder.templates.consumer', 'Consumer embedder extension') }}</option>
                <option value="image_manager">{{ t('extensions.aiBuilder.templates.imageManager', 'Image manager (AdvancedImageUpload)') }}</option>
              </select>
              <div class="hint muted">
                {{
                  t(
                    'extensions.aiBuilder.hints.template',
                    'Templates pre-fill permissions + relationships and give the AI better structure.'
                  )
                }}
              </div>
            </div>

            <div class="form-group">
              <label>{{ t('extensions.aiBuilder.version', 'Version') }}</label>
              <input v-model="spec.version" placeholder="1.0.0" @input="touched.version = true" />
              <div class="hint muted">
                {{
                  t(
                    'extensions.aiBuilder.hints.version',
                    'Manual bump recommended before reinstall to avoid name+version conflicts.'
                  )
                }}
              </div>
            </div>

            <div class="form-group">
              <label>{{ t('extensions.aiBuilder.type', 'Type') }}</label>
              <select v-model="spec.type" @change="touched.type = true">
                <option value="extension">extension</option>
                <option value="widget">widget</option>
              </select>
            </div>

            <div class="form-group">
              <label>{{ t('extensions.aiBuilder.description', 'Description') }}</label>
              <input v-model="spec.description" @input="touched.description = true" />
            </div>
          </div>

          <div class="form-group">
            <label>{{ t('extensions.aiBuilder.goal', 'Goal (optional, for AI)') }}</label>
            <textarea v-model="spec.goal" rows="3" @input="touched.goal = true"></textarea>
            <div class="hint muted">
              {{
                t(
                  'extensions.aiBuilder.hints.goal',
                  'Describe what the extension should do. Mention routes, entities, multilingual content, and relationships.'
                )
              }}
            </div>
          </div>
        </details>

        <details v-show="currentStep === 0" class="section">
          <summary class="section-title">
            {{ t('extensions.aiBuilder.sections.advanced', 'Advanced') }}
          </summary>

          <div class="grid">
            <div class="form-group">
              <label>{{ t('extensions.aiBuilder.apiPrefix', 'API prefix') }}</label>
              <input v-model="spec.api_prefix" placeholder="/api/my" @input="touched.api_prefix = true" />
              <div class="hint muted">
                {{
                  t(
                    'extensions.aiBuilder.hints.apiPrefix',
                    'Keep stable across versions. Recommended: /api/<nameWithoutExtension> (lowercase).'
                  )
                }}
              </div>
            </div>

            <div class="form-group">
              <label>{{ t('extensions.aiBuilder.backendEntry', 'Backend entry') }}</label>
              <input v-model="spec.backend_entry" placeholder="my_extension.py" @input="touched.backend_entry = true" />
            </div>

            <div class="form-group">
              <label>{{ t('extensions.aiBuilder.frontendEntry', 'Frontend entry') }}</label>
              <input v-model="spec.frontend_entry" placeholder="MyExtension.vue" @input="touched.frontend_entry = true" />
            </div>
          </div>

          <div class="form-group">
            <label>{{ t('extensions.aiBuilder.frontendRoutes', 'Frontend routes') }}</label>
            <div class="hint muted">
              {{ t('extensions.aiBuilder.hints.routesForm', 'Add routes for the extension UI. Component should match a .vue file inside the extension package.') }}
            </div>

            <div class="route-grid">
              <div class="route-row header">
                <div>{{ t('extensions.aiBuilder.routes.path', 'Path') }}</div>
                <div>{{ t('extensions.aiBuilder.routes.component', 'Component') }}</div>
                <div>{{ t('extensions.aiBuilder.routes.name', 'Name') }}</div>
                <div>{{ t('extensions.aiBuilder.routes.requiresAuth', 'Auth') }}</div>
                <div></div>
              </div>

              <div v-for="(r, idx) in spec.frontend_routes" :key="idx" class="route-row">
                <input v-model="r.path" @input="touched.frontend_routes = true" placeholder="/my" />
                <input v-model="r.component" @input="touched.frontend_routes = true" placeholder="MyExtension.vue" />
                <input v-model="r.name" @input="touched.frontend_routes = true" placeholder="MyExtension" />
                <input
                  type="checkbox"
                  :checked="routeRequiresAuth(r)"
                  @change="setRouteRequiresAuth(r, ($event.target as HTMLInputElement).checked); touched.frontend_routes = true"
                />
                <button class="button small" type="button" @click="removeRoute(idx)">
                  {{ t('extensions.aiBuilder.routes.remove', 'Remove') }}
                </button>
              </div>
            </div>

            <div class="row" style="margin-top: 0.75rem">
              <button class="button" type="button" @click="addRoute">
                {{ t('extensions.aiBuilder.routes.add', 'Add route') }}
              </button>
            </div>

            <details class="section" style="margin-top: 0.75rem">
              <summary class="section-title">
                {{ t('extensions.aiBuilder.routes.raw', 'Raw routes JSON (advanced)') }}
              </summary>
              <textarea v-model="frontendRoutesJson" rows="6" class="code" @input="touched.frontend_routes = true"></textarea>
              <div v-if="routesJsonError" class="error">{{ routesJsonError }}</div>
            </details>
          </div>

          <div class="form-group" style="margin-top: 1rem">
            <label>{{ t('extensions.aiBuilder.security.permissions', 'Permissions') }}</label>
            <div class="hint muted">
              {{ t('extensions.aiBuilder.security.permissionsHint', 'Select minimal permissions required by the extension.') }}
            </div>

            <div class="pill-grid">
              <label v-for="p in availablePermissions" :key="p" class="pill">
                <input type="checkbox" :checked="spec.permissions.includes(p)" @change="togglePermission(p)" />
                <span>{{ p }}</span>
              </label>
            </div>
          </div>

          <div class="form-group">
            <label>{{ t('extensions.aiBuilder.security.publicEndpoints', 'Public endpoints') }}</label>
            <div class="hint muted">
              {{ t('extensions.aiBuilder.security.publicEndpointsHint', 'Endpoints that should be accessible without auth (relative to api_prefix).') }}
            </div>

            <div class="row" style="margin-top: 0.25rem">
              <input v-model="newPublicEndpoint" placeholder="/health" style="max-width: 240px" />
              <button class="button" type="button" @click="addPublicEndpoint">
                {{ t('extensions.aiBuilder.security.addPublic', 'Add') }}
              </button>
            </div>

            <ul class="list">
              <li v-for="(ep, idx) in spec.public_endpoints" :key="`${ep}-${idx}`" class="list-item">
                <code>{{ ep }}</code>
                <button class="button small" type="button" @click="removePublicEndpoint(idx)">
                  {{ t('extensions.aiBuilder.security.removePublic', 'Remove') }}
                </button>
              </li>
            </ul>
          </div>
        </details>

        <details v-show="currentStep === 1" v-if="templateKey === 'crud'" open class="section">
          <summary class="section-title">
            {{ t('extensions.aiBuilder.sections.dataModel', 'CRUD Data Model') }}
          </summary>

          <div class="grid">
            <div class="form-group">
              <label>{{ t('extensions.aiBuilder.dataModel.table', 'Table name') }}</label>
              <input v-model="crudModel.table" />
              <div class="hint muted">
                {{ t('extensions.aiBuilder.dataModel.tableHint', 'Use lowercase ext_<extensionbase>_* naming for cleanup.') }}
              </div>
            </div>

            <div class="form-group">
              <label>{{ t('extensions.aiBuilder.dataModel.primaryEntity', 'Entity name (UI/API)') }}</label>
              <input v-model="crudModel.entityName" placeholder="items" />
            </div>
          </div>

          <div class="form-group">
            <label>{{ t('extensions.aiBuilder.dataModel.fields', 'Fields') }}</label>

            <div class="field-grid">
              <div class="field-row header">
                <div>{{ t('extensions.aiBuilder.dataModel.fieldName', 'Name') }}</div>
                <div>{{ t('extensions.aiBuilder.dataModel.fieldType', 'Type') }}</div>
                <div>{{ t('extensions.aiBuilder.dataModel.required', 'Required') }}</div>
                <div>{{ t('extensions.aiBuilder.dataModel.translatable', 'Translatable') }}</div>
                <div></div>
              </div>

              <div v-for="(f, idx) in crudModel.fields" :key="idx" class="field-row">
                <input v-model="f.name" placeholder="title" />
                <select v-model="f.type">
                  <option value="text">text</option>
                  <option value="int">int</option>
                  <option value="bool">bool</option>
                  <option value="json">json</option>
                  <option value="timestamp">timestamp</option>
                </select>
                <input type="checkbox" v-model="f.required" />
                <input type="checkbox" v-model="f.translatable" />
                <button class="button small" type="button" @click="removeCrudField(idx)">
                  {{ t('extensions.aiBuilder.dataModel.remove', 'Remove') }}
                </button>
              </div>
            </div>

            <div class="row" style="margin-top: 0.75rem">
              <button class="button" type="button" @click="addCrudField">
                {{ t('extensions.aiBuilder.dataModel.addField', 'Add field') }}
              </button>

              <button class="button" type="button" @click="applyCrudModelToGoal(false)">
                {{ t('extensions.aiBuilder.dataModel.appendToGoal', 'Append to Goal') }}
              </button>

              <button class="button button-primary" type="button" @click="applyCrudModelToGoal(true)">
                {{ t('extensions.aiBuilder.dataModel.replaceGoal', 'Replace Goal') }}
              </button>
            </div>
          </div>

          <div class="form-group" style="margin-top: 1.25rem">
            <label>{{ t('extensions.aiBuilder.dataModel.extraEntities', 'Additional entities (v2)') }}</label>
            <div class="hint muted">
              {{
                t(
                  'extensions.aiBuilder.dataModel.extraEntitiesHint',
                  'Use this when your extension needs multiple tables/entities (e.g. records + settings). This generates multiple CRUD blocks in the Goal.'
                )
              }}
            </div>

            <div v-if="extraCrudModels.length" class="field-grid" style="margin-top: 0.5rem">
              <div
                v-for="(m, midx) in extraCrudModels"
                :key="midx"
                class="section"
                style="margin-top: 0"
              >
                <div class="grid">
                  <div class="form-group">
                    <label>{{ t('extensions.aiBuilder.dataModel.table', 'Table name') }}</label>
                    <input v-model="m.table" />
                  </div>
                  <div class="form-group">
                    <label>{{ t('extensions.aiBuilder.dataModel.primaryEntity', 'Entity name (UI/API)') }}</label>
                    <input v-model="m.entityName" placeholder="records" />
                  </div>
                </div>

                <div class="form-group">
                  <label>{{ t('extensions.aiBuilder.dataModel.fields', 'Fields') }}</label>

                  <div class="field-grid">
                    <div class="field-row header">
                      <div>{{ t('extensions.aiBuilder.dataModel.fieldName', 'Name') }}</div>
                      <div>{{ t('extensions.aiBuilder.dataModel.fieldType', 'Type') }}</div>
                      <div>{{ t('extensions.aiBuilder.dataModel.required', 'Required') }}</div>
                      <div>{{ t('extensions.aiBuilder.dataModel.translatable', 'Translatable') }}</div>
                      <div></div>
                    </div>

                    <div v-for="(f, fidx) in m.fields" :key="fidx" class="field-row">
                      <input v-model="f.name" placeholder="title" />
                      <select v-model="f.type">
                        <option value="text">text</option>
                        <option value="int">int</option>
                        <option value="bool">bool</option>
                        <option value="json">json</option>
                        <option value="timestamp">timestamp</option>
                      </select>
                      <input type="checkbox" v-model="f.required" />
                      <input type="checkbox" v-model="f.translatable" />
                      <button class="button small" type="button" @click="removeCrudFieldForModel(midx, fidx)">
                        {{ t('extensions.aiBuilder.dataModel.remove', 'Remove') }}
                      </button>
                    </div>
                  </div>

                  <div class="row" style="margin-top: 0.75rem">
                    <button class="button" type="button" @click="addCrudFieldForModel(midx)">
                      {{ t('extensions.aiBuilder.dataModel.addField', 'Add field') }}
                    </button>
                    <button class="button" type="button" @click="removeCrudModel(midx)">
                      {{ t('extensions.aiBuilder.dataModel.removeEntity', 'Remove entity') }}
                    </button>
                  </div>
                </div>
              </div>
            </div>

            <div class="row" style="margin-top: 0.75rem">
              <button class="button" type="button" @click="addCrudModel">
                {{ t('extensions.aiBuilder.dataModel.addEntity', 'Add entity') }}
              </button>
            </div>
          </div>
        </details>

        <details v-show="currentStep === 2" open class="section">
          <summary class="section-title">
            {{ t('extensions.aiBuilder.sections.relationships', 'Relationships') }}
          </summary>

          <div class="form-group">
            <label>{{ t('extensions.aiBuilder.relationships.provides', 'Provides: content embedders') }}</label>
            <div class="hint muted">
              {{ t('extensions.aiBuilder.relationships.providesHint', 'Define embedders that other extensions can use (manifest.provides.content_embedders).') }}
            </div>

            <div class="embedder-grid">
              <div class="embedder-row header">
                <div>{{ t('extensions.aiBuilder.relationships.type', 'Type') }}</div>
                <div>{{ t('extensions.aiBuilder.relationships.component', 'Component') }}</div>
                <div>{{ t('extensions.aiBuilder.relationships.label', 'Label i18n key') }}</div>
                <div></div>
              </div>

              <div v-for="(e, idx) in providerEmbedders" :key="idx" class="embedder-row">
                <input v-model="e.typeKey" placeholder="product" @input="syncProviderEmbeddersToSpec" />
                <input v-model="e.component" placeholder="ProductSelector" @input="autoFillEmbedderLabel(e); syncProviderEmbeddersToSpec()" />
                <input v-model="e.label" placeholder="my.embedders.ProductSelector.title" @input="syncProviderEmbeddersToSpec" />
                <button class="button small" type="button" @click="removeProviderEmbedder(idx)">
                  {{ t('extensions.aiBuilder.relationships.remove', 'Remove') }}
                </button>
              </div>
            </div>

            <div class="row" style="margin-top: 0.75rem">
              <button class="button" type="button" @click="addProviderEmbedder">
                {{ t('extensions.aiBuilder.relationships.addProvider', 'Add provider embedder') }}
              </button>
            </div>

            <details class="section" style="margin-top: 0.75rem">
              <summary class="section-title">
                {{ t('extensions.aiBuilder.relationships.advancedFields', 'Advanced embedder fields') }}
              </summary>
              <div v-for="(e, idx) in providerEmbedders" :key="`adv-${idx}`" class="grid">
                <div class="form-group">
                  <label>{{ t('extensions.aiBuilder.relationships.formatApi', 'format_api') }}</label>
                  <input v-model="e.format_api" placeholder="format_item_html" @input="syncProviderEmbeddersToSpec" />
                </div>
                <div class="form-group">
                  <label>{{ t('extensions.aiBuilder.relationships.uiTranslationsApi', 'ui_translations_api') }}</label>
                  <input v-model="e.ui_translations_api" placeholder="get_ui_translations" @input="syncProviderEmbeddersToSpec" />
                </div>
                <div class="form-group" style="grid-column: 1 / -1">
                  <label>{{ t('extensions.aiBuilder.relationships.description', 'Description') }}</label>
                  <input v-model="e.description" placeholder="Embed items from this extension" @input="syncProviderEmbeddersToSpec" />
                </div>
              </div>
            </details>
          </div>

          <div class="form-group" style="margin-top: 1rem">
            <label>{{ t('extensions.aiBuilder.relationships.consumes', 'Consumes: desired embedders') }}</label>
            <div class="hint muted">
              {{ t('extensions.aiBuilder.relationships.consumesHint', 'Declare which embedder types you want to consume (manifest.consumes.content_embedders).') }}
            </div>

            <div class="embedder-grid">
              <div class="embedder-row header">
                <div>{{ t('extensions.aiBuilder.relationships.type', 'Type') }}</div>
                <div>{{ t('extensions.aiBuilder.relationships.providers', 'Provider extensions (comma-separated)') }}</div>
                <div></div>
              </div>

              <div v-for="(c, idx) in consumerEmbedders" :key="idx" class="embedder-row consumes">
                <input v-model="c.typeKey" placeholder="product" @input="syncConsumerEmbeddersToSpec" />
                <input v-model="c.providersCsv" placeholder="StoreExtension, BlogExtension" @input="syncConsumerEmbeddersToSpec" />
                <button class="button small" type="button" @click="removeConsumerEmbedder(idx)">
                  {{ t('extensions.aiBuilder.relationships.remove', 'Remove') }}
                </button>
              </div>
            </div>

            <div class="row" style="margin-top: 0.75rem">
              <button class="button" type="button" @click="addConsumerEmbedder">
                {{ t('extensions.aiBuilder.relationships.addConsumer', 'Add consumer request') }}
              </button>
            </div>
          </div>
        </details>

        <div v-show="currentStep === 0" class="grid">
          <div class="form-group">
            <label>{{ t('extensions.aiBuilder.useAi', 'Use AI (OpenRouter/Groq)') }}</label>
            <select v-model="useAi">
              <option :value="true">true</option>
              <option :value="false">false</option>
            </select>
          </div>

          <div class="form-group">
            <label>{{ t('extensions.aiBuilder.aiProvider', 'AI provider') }}</label>
            <select v-model="aiProvider" :disabled="!useAi">
              <option value="auto">auto</option>
              <option value="groq">groq</option>
              <option value="openrouter">openrouter</option>
            </select>
          </div>
          <div class="form-group">
            <label>{{ t('extensions.aiBuilder.model', 'Model (optional)') }}</label>
            <input v-model="model" placeholder="meta-llama/llama-3.1-8b-instruct:free" />
          </div>
        </div>

        <details v-show="currentStep === 3" open class="section">
          <summary class="section-title">
            {{ t('extensions.aiBuilder.sections.review', 'Review') }}
          </summary>

          <div class="grid">
            <div class="form-group">
              <label>{{ t('extensions.aiBuilder.review.extensionId', 'Extension ID') }}</label>
              <code>{{ extensionId }}</code>
            </div>

            <div class="form-group">
              <label>{{ t('extensions.aiBuilder.review.zipStructure', 'ZIP structure (preview)') }}</label>
              <ul class="files">
                <li v-for="p in zipPathsPreview" :key="p"><code>{{ p }}</code></li>
              </ul>
            </div>
          </div>

          <div class="form-group">
            <label>{{ t('extensions.aiBuilder.review.manifest', 'manifest.json (preview)') }}</label>
            <textarea class="code" :value="manifestPreviewText" rows="12" readonly></textarea>
          </div>
        </details>

        <div class="row" v-show="currentStep === 0">
          <button class="button" :disabled="busy || !useAi || !spec.goal" @click="clarify">
            {{ busy ? t('extensions.aiBuilder.clarifying', 'Thinking...') : t('extensions.aiBuilder.clarify', 'AI Suggest Spec') }}
          </button>
        </div>

        <div class="row" v-show="currentStep === 4">
          <button class="button" :disabled="busy" @click="generate">
            {{ busy ? t('extensions.aiBuilder.generating', 'Generating...') : t('extensions.aiBuilder.generate', 'Generate ZIP') }}
          </button>
          <button class="button" :disabled="busy || !generatedZipBase64" @click="downloadZip">
            {{ t('extensions.aiBuilder.download', 'Download ZIP') }}
          </button>
        </div>

        <div class="row" v-show="currentStep === 6">
          <button class="button button-primary" :disabled="busy || !generatedZipBase64" @click="install">
            {{ busy ? t('extensions.aiBuilder.installing', 'Installing...') : t('extensions.aiBuilder.install', 'Upload & Install') }}
          </button>
        </div>

        <div v-if="error" class="error">{{ error }}</div>
        <div v-if="success" class="success">{{ success }}</div>

        <div v-if="clarifyNotes.length" class="warn">
          <h3>{{ t('extensions.aiBuilder.clarifyNotes', 'AI notes') }}</h3>
          <ul>
            <li v-for="n in clarifyNotes" :key="n">{{ n }}</li>
          </ul>
        </div>

        <div v-if="clarifyQuestions.length" class="warn">
          <h3>{{ t('extensions.aiBuilder.clarifyQuestions', 'Clarifying questions') }}</h3>
          <ul>
            <li v-for="q in clarifyQuestions" :key="q.id">
              <strong>{{ q.question }}</strong>
              <div v-if="q.suggestions?.length" class="muted" style="margin-top: 0.25rem">
                {{ q.suggestions.join(' / ') }}
              </div>
            </li>
          </ul>
        </div>
      </div>
    </div>

    <div v-if="report" v-show="currentStep === 5" class="card" :style="cardStyle">
      <div class="card-content">
        <h2>{{ t('extensions.aiBuilder.report', 'Build report') }}</h2>
        <p><strong>ID:</strong> {{ report.extension_id }}</p>

        <div v-if="report.warnings?.length" class="warn">
          <h3>{{ t('extensions.aiBuilder.warnings', 'Warnings') }}</h3>
          <ul>
            <li v-for="w in report.warnings" :key="w.code">
              <button class="link" @click="openFromWarning(w.code, w.message)">
                <code>{{ w.code }}</code> — {{ w.message }}
              </button>
            </li>
          </ul>
          <div class="hint muted">
            {{ t('extensions.aiBuilder.hints.warningClick', 'Click a warning to open the related file in the editor (when available).') }}
          </div>
        </div>

        <h3>{{ t('extensions.aiBuilder.files', 'Files') }}</h3>
        <ul class="files">
          <li v-for="f in report.files" :key="f"><code>{{ f }}</code></li>
        </ul>
      </div>
    </div>

    <div v-if="filePaths.length" v-show="currentStep === 5" class="card" :style="cardStyle">
      <div class="card-content" id="ai-editor">
        <div class="editor-header">
          <h2>{{ t('extensions.aiBuilder.editor.title', 'Edit generated files') }}</h2>
          <div class="row">
            <button class="button" :disabled="busy" @click="rebuildFromEdits">
              {{ busy ? t('extensions.aiBuilder.editor.rebuilding', 'Rebuilding...') : t('extensions.aiBuilder.editor.rebuild', 'Rebuild ZIP from edits') }}
            </button>
          </div>
        </div>

        <p class="muted">
          {{
            t(
              'extensions.aiBuilder.editor.versionNote',
              'Tip: change the Version field above before rebuilding to avoid name+version conflicts on upload.'
            )
          }}
        </p>

        <div class="editor-grid">
          <div class="file-list">
            <button
              v-for="p in filePaths"
              :key="p"
              class="file-item"
              :class="{ active: p === selectedFile }"
              @click="selectedFile = p"
            >
              <code>{{ p }}</code>
            </button>
          </div>

          <div class="file-editor">
            <div class="file-editor-header">
              <strong><code>{{ selectedFile }}</code></strong>
            </div>
            <textarea v-model="selectedFileContent" class="code" rows="18"></textarea>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

  <script setup lang="ts">
import { computed, nextTick, reactive, ref, watch } from 'vue'
import http from '@/utils/dynamic-http'
import { useI18n } from '@/utils/i18n'
import { useSettingsStore } from '@/stores/settings'

const { t } = useI18n()
const settingsStore = useSettingsStore()

const isRecord = (v: unknown): v is Record<string, unknown> =>
  typeof v === 'object' && v !== null

const getHttpErrorMessage = (e: unknown): string => {
  // Best-effort extraction of backend `detail`.
  if (isRecord(e)) {
    const resp = e.response
    if (isRecord(resp)) {
      const data = resp.data
      if (isRecord(data) && 'detail' in data) {
        const detail = data.detail
        if (typeof detail === 'string') return detail
        try {
          // Pydantic validation errors are typically arrays of objects.
          return JSON.stringify(detail, null, 2)
        } catch {
          return String(detail)
        }
      }
    }
    if (typeof e.message === 'string') return e.message
  }
  return String(e)
}

type ExtensionSpec = {
  name: string
  version: string
  type: 'extension' | 'widget'
  description: string
  author: string
  api_prefix: string
  backend_entry: string
  frontend_entry: string
  frontend_components: string[]
  frontend_routes: FrontendRoute[]
  locales: { supported: string[]; default: string; directory: string }
  permissions: string[]
  public_endpoints: string[]
  dependencies: Record<string, unknown>
  provides?: ProvidesConfig
  consumes?: ConsumesConfig
  goal?: string
}

type FrontendRoute = {
  path: string
  component: string
  name?: string
  meta?: Record<string, unknown>
  props?: boolean
}

type ProviderEmbedderConfig = {
  label: string
  component: string
  format_api?: string
  ui_translations_api?: string
  description?: string
}

type ProvidesConfig = {
  content_embedders?: Record<string, ProviderEmbedderConfig>
}

type ConsumesConfig = {
  content_embedders?: Record<string, string[]>
}

type BuildReport = {
  extension_id: string
  files: string[]
  warnings: Array<{ code: string; message: string }>
}

type ClarifyQuestion = {
  id: string
  question: string
  suggestions: string[]
}

type CrudFieldType = 'text' | 'int' | 'bool' | 'json' | 'timestamp'
type CrudField = {
  name: string
  type: CrudFieldType
  required: boolean
  translatable: boolean
}

type CrudEntityModel = {
  table: string
  entityName: string
  fields: CrudField[]
}

type ProviderEmbedder = {
  typeKey: string
  label: string
  component: string
  format_api?: string
  ui_translations_api?: string
  description?: string
}

type ConsumerEmbedder = {
  typeKey: string
  providersCsv: string
}

const cardStyle = computed(() => ({
  backgroundColor: settingsStore.styleSettings.cardBg,
  color: settingsStore.styleSettings.textPrimary,
  borderColor: settingsStore.styleSettings.cardBorder
}))

const busy = ref(false)
const error = ref('')
const success = ref('')
const installedOk = ref(false)
const clarifyQuestions = ref<ClarifyQuestion[]>([])
const clarifyNotes = ref<string[]>([])
const report = ref<BuildReport | null>(null)
const generatedZipBase64 = ref<string>('')
const filesText = ref<Record<string, string>>({})
const selectedFile = ref<string>('')
const useAi = ref(true)
const aiProvider = ref<'auto' | 'groq' | 'openrouter'>('auto')
const model = ref('')
const routesJsonError = ref('')
const templateKey = ref<'simple' | 'crud' | 'crud_multilingual' | 'provider_embedder' | 'consumer_embedder' | 'image_manager'>('simple')

const availablePermissions = [
  'database_read',
  'database_write'
] as const

const togglePermission = (perm: (typeof availablePermissions)[number]) => {
  const set = new Set(spec.value.permissions || [])
  if (set.has(perm)) set.delete(perm)
  else set.add(perm)
  spec.value.permissions = Array.from(set)
}

const newPublicEndpoint = ref('')

const addPublicEndpoint = () => {
  const raw = (newPublicEndpoint.value || '').trim()
  if (!raw) return
  const ep = raw.startsWith('/') ? raw : `/${raw}`
  if (!Array.isArray(spec.value.public_endpoints)) spec.value.public_endpoints = []
  if (!spec.value.public_endpoints.includes(ep)) {
    spec.value.public_endpoints.push(ep)
  }
  newPublicEndpoint.value = ''
}

const removePublicEndpoint = (idx: number) => {
  spec.value.public_endpoints.splice(idx, 1)
}

const steps = computed(() => [
  { key: 'basic', label: t('extensions.aiBuilder.steps.basic', 'Basic') },
  { key: 'model', label: t('extensions.aiBuilder.steps.model', 'Model') },
  { key: 'relationships', label: t('extensions.aiBuilder.steps.relationships', 'Relationships') },
  { key: 'review', label: t('extensions.aiBuilder.steps.review', 'Review') },
  { key: 'generate', label: t('extensions.aiBuilder.steps.generate', 'Generate') },
  { key: 'fix', label: t('extensions.aiBuilder.steps.fix', 'Fix') },
  { key: 'install', label: t('extensions.aiBuilder.steps.install', 'Install') }
])

const currentStep = ref(0)

const stepEnabled = (idx: number): boolean => {
  // Hide the Model step when not using CRUD template.
  if (idx === 1) return templateKey.value === 'crud' || templateKey.value === 'crud_multilingual'
  return true
}

const goStep = (idx: number) => {
  const max = steps.value.length - 1
  let i = Math.max(0, Math.min(max, idx))
  // Skip disabled steps
  if (!stepEnabled(i)) {
    // Prefer forward
    if (i < max) i = i + 1
    else i = i - 1
  }
  currentStep.value = i
}

const nextStep = () => {
  const max = steps.value.length - 1
  let i = currentStep.value + 1
  while (i <= max && !stepEnabled(i)) i++
  goStep(i)
}

const prevStep = () => {
  let i = currentStep.value - 1
  while (i >= 0 && !stepEnabled(i)) i--
  goStep(i)
}

const isStepDone = (idx: number): boolean => {
  if (idx === 0) {
    return Boolean(spec.value.name && spec.value.version && spec.value.api_prefix)
  }
  if (idx === 1) {
    if (templateKey.value !== 'crud' && templateKey.value !== 'crud_multilingual') return true
    return crudModel.fields.some(f => (f.name || '').trim())
  }
  if (idx === 4) {
    return Boolean(generatedZipBase64.value)
  }
  if (idx === 5) {
    return filePaths.value.length > 0
  }
  if (idx === 6) {
    return installedOk.value
  }
  return true
}

const extensionId = computed(() => `${spec.value.name}_${spec.value.version}`)

const manifestPreview = computed<Record<string, unknown>>(() => {
  const localesDirRaw = spec.value.locales?.directory || 'locales/'
  const localesDir = localesDirRaw.endsWith('/') ? localesDirRaw : `${localesDirRaw}/`

  const base: Record<string, unknown> = {
    name: spec.value.name,
    version: spec.value.version,
    type: spec.value.type,
    description: spec.value.description,
    author: spec.value.author,
    backend_entry: spec.value.backend_entry,
    frontend_entry: spec.value.frontend_entry,
    frontend_components: spec.value.frontend_components,
    frontend_routes: spec.value.frontend_routes,
    locales: {
      supported: spec.value.locales?.supported || ['en', 'bg'],
      default: spec.value.locales?.default || 'en',
      directory: localesDir
    },
    permissions: spec.value.permissions,
    public_endpoints: spec.value.public_endpoints,
    dependencies: spec.value.dependencies
  }

  if (spec.value.provides) base.provides = spec.value.provides
  if (spec.value.consumes) base.consumes = spec.value.consumes

  return base
})

const manifestPreviewText = computed(() => JSON.stringify(manifestPreview.value, null, 2))

const zipPathsPreview = computed(() => {
  const localesDirRaw = spec.value.locales?.directory || 'locales/'
  const localesDir = localesDirRaw.endsWith('/') ? localesDirRaw : `${localesDirRaw}/`
  const langs = spec.value.locales?.supported || ['en', 'bg']
  const localeFiles = langs.map(l => `${localesDir}${l}.json`)

  // Provider embedder components (if any)
  const providedComponents: string[] = []
  const ce = spec.value.provides?.content_embedders
  if (ce) {
    for (const cfg of Object.values(ce)) {
      const comp = cfg.component
      if (typeof comp === 'string' && comp.trim()) {
        const file = comp.endsWith('.vue') ? comp : `${comp}.vue`
        providedComponents.push(`frontend/${file}`)
      }
    }
  }

  return [
    'manifest.json',
    `backend/${spec.value.backend_entry}`,
    `frontend/${spec.value.frontend_entry}`,
    ...providedComponents,
    ...localeFiles
  ]
})

const touched = reactive({
  name: false,
  version: false,
  type: false,
  description: false,
  goal: false,
  api_prefix: false,
  backend_entry: false,
  frontend_entry: false,
  frontend_routes: false
})

const filePaths = computed(() => Object.keys(filesText.value || {}).sort())

const selectedFileContent = computed({
  get: () => {
    if (!selectedFile.value) return ''
    return filesText.value[selectedFile.value] ?? ''
  },
  set: (v: string) => {
    if (!selectedFile.value) return
    filesText.value = { ...filesText.value, [selectedFile.value]: v }
  }
})

const _deriveNamespace = (name: string): string => {
  const base = (name || '').replace(/Extension$/i, '').trim() || name
  return base.toLowerCase().replace(/[^a-z0-9]/g, '')
}

const _toSnakeCase = (name: string): string => {
  const s = (name || '')
    .replace(/Extension$/i, '')
    .replace(/([a-z0-9])([A-Z])/g, '$1_$2')
    .replace(/\W+/g, '_')
    .toLowerCase()
    .replace(/^_+|_+$/g, '')
  return s || 'my_extension'
}

const spec = ref<ExtensionSpec>({
  name: 'MyExtension',
  version: '1.0.0',
  type: 'extension',
  description: 'AI generated extension',
  author: 'AI',
  api_prefix: '/api/my',
  backend_entry: 'my_extension.py',
  frontend_entry: 'MyExtension.vue',
  frontend_components: [],
  frontend_routes: [
    {
      path: '/my',
      component: 'MyExtension.vue',
      name: 'MyExtension',
      meta: { requiresAuth: true }
    }
  ],
  locales: { supported: ['en', 'bg'], default: 'en', directory: 'locales/' },
  permissions: [],
  public_endpoints: [],
  dependencies: {},
  goal: ''
})

const crudModel = reactive<{ table: string; entityName: string; fields: CrudField[] }>({
  table: '',
  entityName: 'items',
  fields: [
    { name: 'title', type: 'text', required: true, translatable: true },
    { name: 'description', type: 'text', required: false, translatable: true }
  ]
})

// V2 (stage 1): allow multiple CRUD entities (extra tables) and generate a richer goal block.
const extraCrudModels = reactive<CrudEntityModel[]>([])

const providerEmbedders = reactive<ProviderEmbedder[]>([])
const consumerEmbedders = reactive<ConsumerEmbedder[]>([])

const autoFillEmbedderLabel = (e: ProviderEmbedder) => {
  if (e.label) return
  if (!e.component) return
  const ns = _deriveNamespace(spec.value.name) || 'my'
  const comp = (e.component || '').replace(/\.vue$/i, '').trim()
  if (!comp) return
  e.label = `${ns}.embedders.${comp}.title`
}

const syncProviderEmbeddersToSpec = () => {
  const map: Record<string, ProviderEmbedderConfig> = {}
  for (const e of providerEmbedders) {
    const key = (e.typeKey || '').trim()
    const component = (e.component || '').trim()
    if (!key || !component) continue
    map[key] = {
      label: (e.label || '').trim() || `${_deriveNamespace(spec.value.name) || 'my'}.embedders.${component.replace(/\.vue$/i, '')}.title`,
      component,
      ...(e.format_api ? { format_api: e.format_api } : {}),
      ...(e.ui_translations_api ? { ui_translations_api: e.ui_translations_api } : {}),
      ...(e.description ? { description: e.description } : {})
    }
  }

  if (Object.keys(map).length) {
    spec.value.provides = { ...(spec.value.provides || {}), content_embedders: map }
  } else {
    // If nothing provided, remove provides if it only contained content_embedders.
    const rest: ProvidesConfig = { ...(spec.value.provides || {}) }
    delete rest.content_embedders
    spec.value.provides = Object.keys(rest).length ? rest : undefined
  }
}

const addProviderEmbedder = () => {
  providerEmbedders.push({
    typeKey: '',
    component: '',
    label: '',
    format_api: 'format_item_html',
    ui_translations_api: 'get_ui_translations',
    description: ''
  })
}

const removeProviderEmbedder = (idx: number) => {
  providerEmbedders.splice(idx, 1)
  syncProviderEmbeddersToSpec()
}

const syncConsumerEmbeddersToSpec = () => {
  const map: Record<string, string[]> = {}
  for (const c of consumerEmbedders) {
    const typeKey = (c.typeKey || '').trim()
    if (!typeKey) continue
    const providers = (c.providersCsv || '')
      .split(',')
      .map(s => s.trim())
      .filter(Boolean)
    if (!providers.length) continue
    map[typeKey] = providers
  }

  if (Object.keys(map).length) {
    spec.value.consumes = { ...(spec.value.consumes || {}), content_embedders: map }
  } else {
    const rest: ConsumesConfig = { ...(spec.value.consumes || {}) }
    delete rest.content_embedders
    spec.value.consumes = Object.keys(rest).length ? rest : undefined
  }
}

const routeRequiresAuth = (r: FrontendRoute): boolean => {
  return Boolean(r?.meta?.requiresAuth)
}

const setRouteRequiresAuth = (r: FrontendRoute, value: boolean) => {
  const current = r.meta && typeof r.meta === 'object' ? r.meta : {}
  r.meta = { ...current, requiresAuth: value }
}

const addRoute = () => {
  const ns = _deriveNamespace(spec.value.name) || 'my'
  if (!Array.isArray(spec.value.frontend_routes)) spec.value.frontend_routes = []
  spec.value.frontend_routes.push({
    path: `/${ns}`,
    component: spec.value.frontend_entry,
    name: spec.value.name,
    meta: { requiresAuth: true }
  })
}

const removeRoute = (idx: number) => {
  spec.value.frontend_routes.splice(idx, 1)
}

const addConsumerEmbedder = () => {
  consumerEmbedders.push({ typeKey: '', providersCsv: '' })
}

const removeConsumerEmbedder = (idx: number) => {
  consumerEmbedders.splice(idx, 1)
  syncConsumerEmbeddersToSpec()
}

const addCrudField = () => {
  crudModel.fields.push({ name: '', type: 'text', required: false, translatable: false })
}

const removeCrudField = (idx: number) => {
  crudModel.fields.splice(idx, 1)
}

const addCrudModel = () => {
  const ns = _deriveNamespace(spec.value.name)
  extraCrudModels.push({
    table: `ext_${ns || 'my'}_table`,
    entityName: 'records',
    fields: [{ name: 'title', type: 'text', required: true, translatable: true }]
  })
}

const removeCrudModel = (idx: number) => {
  extraCrudModels.splice(idx, 1)
}

const addCrudFieldForModel = (modelIdx: number) => {
  const m = extraCrudModels[modelIdx]
  if (!m) return
  m.fields.push({ name: '', type: 'text', required: false, translatable: false })
}

const removeCrudFieldForModel = (modelIdx: number, fieldIdx: number) => {
  const m = extraCrudModels[modelIdx]
  if (!m) return
  m.fields.splice(fieldIdx, 1)
}

const _crudDefaultTable = () => {
  const ns = _deriveNamespace(spec.value.name)
  return `ext_${ns || 'my'}_items`
}

const _crudEntityToGoalBlock = (m: CrudEntityModel, title: string) => {
  const ns = _deriveNamespace(spec.value.name)
  const entity = (m.entityName || 'items').trim()
  const table = (m.table || _crudDefaultTable()).trim()

  const fields = (m.fields || [])
    .filter(f => (f.name || '').trim())
    .map(f => {
      const flags = [f.required ? 'required' : 'optional', f.translatable ? 'translatable' : 'not translatable']
      return `- ${f.name.trim()}: ${f.type} (${flags.join(', ')})`
    })
    .join('\n')

  const translatableFields = (m.fields || [])
    .filter(f => (f.name || '').trim() && f.translatable)
    .map(f => f.name.trim())

  const translationsNote = translatableFields.length
    ? `Translatable fields: ${translatableFields.join(', ')}. Use an extension translations table (e.g. ext_${ns || 'my'}_translations with (record_id, language_code, translation_data JSONB) UNIQUE) and merge translations on reads.`
    : 'No translatable fields.'

  return (
    `${title}\n` +
    `Entity: ${entity}\n` +
    `Main table: ${table} (PostgreSQL, lowercase)\n` +
    `Fields:\n${fields || '- (none)'}\n\n` +
    `API:\n` +
    `- GET ${spec.value.api_prefix}/${entity} (list)\n` +
    `- POST ${spec.value.api_prefix}/${entity} (create)\n` +
    `- PUT ${spec.value.api_prefix}/${entity}/{id} (update)\n` +
    `- DELETE ${spec.value.api_prefix}/${entity}/{id} (delete)\n` +
    `Auth: protect endpoints with require_user.\n` +
    `${translationsNote}`
  )
}

const _crudModelToGoalBlock = () => {
  const blocks: string[] = []
  blocks.push(_crudEntityToGoalBlock(crudModel as unknown as CrudEntityModel, 'CRUD Data Model'))

  for (const extra of extraCrudModels) {
    blocks.push(_crudEntityToGoalBlock(extra, 'CRUD Data Model'))
  }

  return blocks.join('\n\n')
}

const applyCrudModelToGoal = (replace: boolean) => {
  const block = _crudModelToGoalBlock()
  if (replace || !spec.value.goal) {
    spec.value.goal = block
  } else {
    spec.value.goal = `${spec.value.goal}\n\n${block}`
  }
}

// Auto-fill derived fields when name changes, unless user touched those fields.
watch(
  () => spec.value.name,
  newName => {
    const ns = _deriveNamespace(newName)
    if (!touched.api_prefix) spec.value.api_prefix = `/api/${ns || 'my'}`
    if (!touched.backend_entry) spec.value.backend_entry = `${_toSnakeCase(newName)}.py`
    if (!touched.frontend_entry) spec.value.frontend_entry = `${newName || 'MyExtension'}.vue`
    if (!touched.frontend_routes) {
      spec.value.frontend_routes = [
        {
          path: `/${ns || 'my'}`,
          component: spec.value.frontend_entry,
          name: newName || 'MyExtension',
          meta: { requiresAuth: true }
        }
      ]
    }
  }
)

const applyTemplate = (key: typeof templateKey.value) => {
  const ns = _deriveNamespace(spec.value.name)

  if (key === 'simple') {
    spec.value.permissions = []
    spec.value.public_endpoints = []
    spec.value.dependencies = {}
    spec.value.provides = undefined
    spec.value.consumes = undefined
    // do not overwrite user's goal, but provide a helpful placeholder if empty
    if (!spec.value.goal) {
      spec.value.goal = 'A simple extension page that calls its /health endpoint and renders a list.'
    }
    return
  }

  if (key === 'crud') {
    spec.value.permissions = ['database_read', 'database_write']
    spec.value.public_endpoints = []
    spec.value.dependencies = {}
    spec.value.provides = undefined
    spec.value.consumes = undefined
    if (!spec.value.goal) {
      spec.value.goal =
        `CRUD admin UI + API for "items". Create PostgreSQL table ext_${ns || 'my'}_items (lowercase) with id SERIAL, title TEXT, created_at TIMESTAMP. Add list/create/update/delete endpoints and use require_user for auth.`
    }

    // Seed CRUD model defaults
    if (!crudModel.table) crudModel.table = `ext_${ns || 'my'}_items`
    if (!crudModel.entityName) crudModel.entityName = 'items'
    return
  }

  if (key === 'crud_multilingual') {
    spec.value.permissions = ['database_read', 'database_write']
    spec.value.public_endpoints = []
    spec.value.dependencies = {}
    spec.value.provides = undefined
    spec.value.consumes = undefined

    if (!spec.value.goal) {
      spec.value.goal =
        `Multilingual CRUD admin UI + API for "items". ` +
        `Create PostgreSQL table ext_${ns || 'my'}_items (lowercase recommended) with id SERIAL, title TEXT, created_at TIMESTAMP. ` +
        `Also create translations table ext_${ns || 'my'}_translations with (record_id, language_code, translation_data JSONB) UNIQUE(record_id, language_code). ` +
        `Add endpoints for translations: POST/GET/DELETE, and merge translations on reads when language != 'en'. ` +
        `Frontend: implement language tabs for content language (not UI language) and preserve per-language form state.`
    }

    // Seed CRUD model defaults
    if (!crudModel.table) crudModel.table = `ext_${ns || 'my'}_items`
    if (!crudModel.entityName) crudModel.entityName = 'items'

    // Seed default fields if the model is empty.
    const hasAnyField = crudModel.fields.some(f => (f.name || '').trim())
    if (!hasAnyField) {
      crudModel.fields.splice(
        0,
        crudModel.fields.length,
        { name: 'title', type: 'text', required: true, translatable: true },
        { name: 'description', type: 'text', required: false, translatable: true }
      )
    }
    return
  }

  if (key === 'provider_embedder') {
    spec.value.permissions = ['database_read']
    spec.value.public_endpoints = []
    spec.value.dependencies = {}
    spec.value.provides = {
      content_embedders: {
        item: {
          label: `${ns || 'my'}.embedders.ProductSelector.title`,
          component: 'ProductSelector',
          format_api: 'format_item_html',
          ui_translations_api: 'get_ui_translations',
          description: 'Embed items from this extension'
        }
      }
    }
    spec.value.consumes = undefined
    if (!spec.value.goal) {
      spec.value.goal =
        'Provide a content embedder component (ProductSelector.vue) that lets a consumer pick an item. Implement backend APIs: format_item_html and get_ui_translations under the extension api_prefix.'
    }

    // Seed relationship UI
    if (!providerEmbedders.length) {
      providerEmbedders.push({
        typeKey: 'item',
        component: 'ProductSelector',
        label: `${ns || 'my'}.embedders.ProductSelector.title`,
        format_api: 'format_item_html',
        ui_translations_api: 'get_ui_translations',
        description: 'Embed items from this extension'
      })
    }
  }

  if (key === 'consumer_embedder') {
    spec.value.permissions = ['database_read']
    spec.value.public_endpoints = []
    spec.value.dependencies = {}
    spec.value.provides = undefined
    spec.value.consumes = {
      content_embedders: {
        item: ['StoreExtension']
      }
    }

    if (!spec.value.goal) {
      spec.value.goal =
        'Consume a content embedder from another extension (e.g. StoreExtension). ' +
        'Frontend: discover embedders via the relationship system, dynamically load the provider component, and also load provider locales for current UI language. ' +
        'Use i18n.loadExtensionTranslationsForExtension(providerName, currentLanguage) before rendering the embedder component.'
    }

    if (!consumerEmbedders.length) {
      consumerEmbedders.push({ typeKey: 'item', providersCsv: 'StoreExtension' })
    }

    return
  }

  if (key === 'image_manager') {
    spec.value.permissions = ['database_read', 'database_write']
    spec.value.public_endpoints = []
    spec.value.dependencies = {}
    spec.value.provides = undefined
    spec.value.consumes = undefined

    // Add a dedicated admin route (generator will scaffold the component file).
    if (!touched.frontend_routes) {
      spec.value.frontend_routes = [
        {
          path: `/${ns || 'my'}`,
          component: spec.value.frontend_entry,
          name: spec.value.name,
          meta: { requiresAuth: true }
        },
        {
          path: `/${ns || 'my'}/admin`,
          component: `${spec.value.name}Admin.vue`,
          name: `${spec.value.name} Admin`,
          meta: { requiresAuth: true }
        }
      ]
    }

    if (!spec.value.goal) {
      spec.value.goal =
        'Build an image manager UI using the shared AdvancedImageUpload component. ' +
        "Frontend: import AdvancedImageUpload from '@/components/AdvancedImageUpload.vue' and render it in the admin route. " +
        'Backend: implement endpoints under api_prefix: POST /upload-image, GET /images/list, POST /images/folder, POST /images/move, DELETE /images/delete, POST /images/rename. ' +
        'Save files under uploads/<extension-namespace>/ and return URLs suitable for <img src>. '
    }
    return
  }
}

// If spec is populated by AI "clarify" step, hydrate relationship editors once.
watch(
  () => spec.value.provides,
  provides => {
    if (providerEmbedders.length) return
    const ce = provides?.content_embedders
    if (!ce) return
    for (const [typeKey, cfg] of Object.entries(ce)) {
      providerEmbedders.push({
        typeKey,
        label: cfg.label || '',
        component: cfg.component || '',
        format_api: cfg.format_api,
        ui_translations_api: cfg.ui_translations_api,
        description: cfg.description
      })
    }
  }
)

watch(
  () => spec.value.consumes,
  consumes => {
    if (consumerEmbedders.length) return
    const ce = consumes?.content_embedders
    if (!ce) return
    for (const [typeKey, providers] of Object.entries(ce)) {
      consumerEmbedders.push({
        typeKey,
        providersCsv: Array.isArray(providers) ? providers.join(', ') : ''
      })
    }
  }
)

watch(
  () => [templateKey.value, spec.value.name] as const,
  ([key]) => {
    if (key !== 'crud' && key !== 'crud_multilingual') return
    if (!crudModel.table) {
      crudModel.table = _crudDefaultTable()
    }
  }
)

watch(templateKey, key => {
  // Applying a template is an explicit user action, so it's OK to override some fields.
  applyTemplate(key)
})

const frontendRoutesJson = computed({
  get: () => JSON.stringify(spec.value.frontend_routes || [], null, 2),
  set: (v: string) => {
    routesJsonError.value = ''
    try {
      const parsed = JSON.parse(v)
      if (!Array.isArray(parsed)) {
        routesJsonError.value = t('extensions.aiBuilder.routesJsonError', 'Routes JSON must be an array')
        return
      }
      spec.value.frontend_routes = parsed
    } catch (e: unknown) {
      routesJsonError.value = e instanceof Error ? e.message : String(e)
    }
  }
})

const openFileInEditor = async (path: string) => {
  if (!path) return
  if (!filePaths.value.length) {
    error.value = t('extensions.aiBuilder.errors.noFilesYet', 'Generate an extension first to open files in the editor.')
    return
  }
  if (!(path in (filesText.value || {}))) {
    error.value = t('extensions.aiBuilder.errors.fileNotFound', 'File not found in generated output: {path}', { path })
    return
  }
  selectedFile.value = path
  await nextTick()
  const el = document.getElementById('ai-editor')
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

const openFromWarning = async (code: string, message: string) => {
  const msg = message || ''

  const pathMatch = msg.match(/'(frontend\/[^']+)'/) || msg.match(/'(backend\/[^']+)'/)
  if (pathMatch?.[1]) {
    await openFileInEditor(pathMatch[1])
    return
  }

  if (code.startsWith('manifest.')) {
    await openFileInEditor('manifest.json')
    return
  }
  if (code.startsWith('i18n.')) {
    const dirRaw = spec.value.locales?.directory || 'locales/'
    const dir = dirRaw.endsWith('/') ? dirRaw : `${dirRaw}/`
    await openFileInEditor(`${dir}en.json`)
    return
  }
  if (code.startsWith('relationships.')) {
    await openFileInEditor('manifest.json')
    return
  }
  if (code.startsWith('db.')) {
    await openFileInEditor(`backend/${spec.value.backend_entry}`)
    return
  }

  await openFileInEditor('manifest.json')
}

const generate = async () => {
  busy.value = true
  error.value = ''
  success.value = ''
  clarifyQuestions.value = []
  clarifyNotes.value = []
  report.value = null
  generatedZipBase64.value = ''
  filesText.value = {}
  selectedFile.value = ''

  try {
    const res = await http.post('/api/ai/extensions/generate', {
      spec: spec.value,
      instructions: spec.value.goal || null,
      use_ai: useAi.value,
      model: model.value || null,
      ai_provider: useAi.value ? aiProvider.value : 'auto'
    })

    report.value = res.data.report
    generatedZipBase64.value = res.data.zip_base64
    filesText.value = res.data.files_text || {}
    selectedFile.value = filePaths.value[0] || ''
    success.value = t('extensions.aiBuilder.generated', 'ZIP generated successfully')
  } catch (e: unknown) {
    error.value = getHttpErrorMessage(e)
  } finally {
    busy.value = false
  }
}

const clarify = async () => {
  if (!useAi.value || !spec.value.goal) return

  const goalText = spec.value.goal

  busy.value = true
  error.value = ''
  success.value = ''
  clarifyQuestions.value = []
  clarifyNotes.value = []

  try {
    const res = await http.post('/api/ai/extensions/clarify', {
      draft_spec: spec.value,
      goal: spec.value.goal,
      ai_provider: aiProvider.value,
      model: model.value || null
    })

    if (res.data?.suggested_spec) {
      spec.value = res.data.suggested_spec
      // keep goal text as user-entered
      spec.value.goal = goalText
    }
    clarifyQuestions.value = res.data?.questions || []
    clarifyNotes.value = res.data?.notes || []
    success.value = t('extensions.aiBuilder.clarified', 'Spec suggestions applied')
  } catch (e: unknown) {
    error.value = getHttpErrorMessage(e)
  } finally {
    busy.value = false
  }
}

const rebuildFromEdits = async () => {
  if (!filePaths.value.length) return

  busy.value = true
  error.value = ''
  success.value = ''

  try {
    const edited = { ...filesText.value }

    // Keep manifest in sync with the current spec (especially version).
    if (edited['manifest.json']) {
      try {
        const current = JSON.parse(edited['manifest.json'])
        const merged = {
          ...current,
          name: spec.value.name,
          version: spec.value.version,
          type: spec.value.type,
          description: spec.value.description,
          author: spec.value.author,
          backend_entry: spec.value.backend_entry,
          frontend_entry: spec.value.frontend_entry,
          frontend_components: spec.value.frontend_components,
          frontend_routes: spec.value.frontend_routes,
          locales: spec.value.locales,
          permissions: spec.value.permissions,
          public_endpoints: spec.value.public_endpoints,
          dependencies: spec.value.dependencies,
          ...(spec.value.provides ? { provides: spec.value.provides } : {}),
          ...(spec.value.consumes ? { consumes: spec.value.consumes } : {})
        }
        edited['manifest.json'] = JSON.stringify(merged, null, 2)
      } catch {
        // If manifest was made invalid JSON by edits, keep it as-is and let backend warnings surface.
      }
    }

    const res = await http.post('/api/ai/extensions/package', {
      spec: spec.value,
      files_text: edited
    })

    report.value = res.data.report
    generatedZipBase64.value = res.data.zip_base64
    filesText.value = res.data.files_text || edited
    selectedFile.value = selectedFile.value || filePaths.value[0] || ''
    success.value = t('extensions.aiBuilder.editor.rebuilt', 'ZIP rebuilt successfully')
  } catch (e: unknown) {
    error.value = getHttpErrorMessage(e)
  } finally {
    busy.value = false
  }
}

const install = async () => {
  if (!generatedZipBase64.value) return

  busy.value = true
  error.value = ''
  success.value = ''
  installedOk.value = false

  try {
    const bytes = Uint8Array.from(atob(generatedZipBase64.value), c => c.charCodeAt(0))
    const blob = new Blob([bytes], { type: 'application/zip' })
    const fileName = `${spec.value.name}_${spec.value.version}.zip`
    const file = new File([blob], fileName, { type: 'application/zip' })

    const formData = new FormData()
    formData.append('file', file)

    const uploaded = await http.post('/api/extensions/upload', formData)
    const extId = uploaded.data?.id
    if (!extId) {
      success.value = t('extensions.aiBuilder.uploaded', 'Uploaded, but no extension id returned')
      return
    }

    await http.patch(`/api/extensions/${extId}`, { is_enabled: true })
    success.value = t('extensions.aiBuilder.installed', 'Extension uploaded and enabled')
    installedOk.value = true
  } catch (e: unknown) {
    error.value = getHttpErrorMessage(e)
  } finally {
    busy.value = false
  }
}

const downloadZip = () => {
  if (!generatedZipBase64.value) return

  const bytes = Uint8Array.from(atob(generatedZipBase64.value), c => c.charCodeAt(0))
  const blob = new Blob([bytes], { type: 'application/zip' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${spec.value.name}_${spec.value.version}.zip`
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}
</script>

<style scoped>
.muted {
  opacity: 0.8;
}

.hint {
  font-size: 0.85rem;
  line-height: 1.25rem;
}

.section {
  margin-top: 0.75rem;
  padding: 0.5rem;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 12px;
}

.section-title {
  cursor: pointer;
  user-select: none;
  font-weight: 600;
  opacity: 0.95;
}

.card {
  margin-top: 1rem;
  border: 1px solid;
  border-radius: 12px;
}

.stepper {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 0.5rem;
}

.step {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.6rem 0.7rem;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.14);
  background: transparent;
  color: inherit;
  cursor: pointer;
  text-align: left;
}

.step.active {
  border-color: rgba(76, 175, 80, 0.8);
  background: rgba(76, 175, 80, 0.12);
}

.step.done {
  border-color: rgba(76, 175, 80, 0.35);
}

.step-index {
  display: inline-flex;
  width: 22px;
  height: 22px;
  border-radius: 999px;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(255, 255, 255, 0.2);
  font-size: 0.85rem;
  opacity: 0.9;
}

.step-label {
  font-size: 0.9rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.card-content {
  padding: 1.25rem;
}

.grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.75rem;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  margin-top: 0.75rem;
}

input,
select,
textarea {
  padding: 0.65rem;
  border-radius: 10px;
  border: 1px solid var(--border-color);
  background-color: var(--input-bg);
  color: var(--text-primary);
}

/* Fix dark-theme native select dropdown readability (option list). */
select option {
  background-color: var(--card-bg);
  color: var(--text-primary);
}

.row {
  display: flex;
  gap: 0.75rem;
  margin-top: 1rem;
}

.button.small {
  padding: 0.45rem 0.7rem;
  border-radius: 8px;
}

.field-grid {
  display: grid;
  gap: 0.5rem;
}

.field-row {
  display: grid;
  grid-template-columns: 1fr 160px 120px 140px 120px;
  gap: 0.5rem;
  align-items: center;
}

.field-row.header {
  opacity: 0.85;
  font-size: 0.9rem;
}

.field-row input[type="checkbox"] {
  width: 18px;
  height: 18px;
  padding: 0;
}

.route-grid {
  display: grid;
  gap: 0.5rem;
  margin-top: 0.5rem;
}

.route-row {
  display: grid;
  grid-template-columns: 200px 1fr 180px 80px 120px;
  gap: 0.5rem;
  align-items: center;
}

.route-row.header {
  opacity: 0.85;
  font-size: 0.9rem;
}

.route-row input[type="checkbox"] {
  width: 18px;
  height: 18px;
  padding: 0;
}

.pill-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.5rem;
}

.pill {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.45rem 0.65rem;
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 999px;
  cursor: pointer;
}

.pill input[type="checkbox"] {
  width: 18px;
  height: 18px;
}

.list {
  margin: 0.5rem 0 0;
  padding-left: 1.25rem;
}

.list-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  margin: 0.35rem 0;
}

.embedder-grid {
  display: grid;
  gap: 0.5rem;
  margin-top: 0.5rem;
}

.embedder-row {
  display: grid;
  grid-template-columns: 160px 220px 1fr 120px;
  gap: 0.5rem;
  align-items: center;
}

.embedder-row.consumes {
  grid-template-columns: 160px 1fr 120px;
}

.embedder-row.header {
  opacity: 0.85;
  font-size: 0.9rem;
}

.button {
  padding: 0.7rem 1rem;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.2);
  background: transparent;
  color: inherit;
  cursor: pointer;
}

.button-primary {
  background: rgba(76, 175, 80, 0.25);
}

.button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.link {
  background: transparent;
  border: 0;
  padding: 0;
  color: inherit;
  cursor: pointer;
  text-align: left;
}

.link code {
  text-decoration: underline;
}

.error {
  margin-top: 0.75rem;
  color: #ff6b6b;
}

.success {
  margin-top: 0.75rem;
  color: #4caf50;
}

.warn {
  margin-top: 0.75rem;
  padding: 0.75rem;
  border: 1px solid rgba(255, 200, 0, 0.25);
  border-radius: 10px;
}

.files {
  margin: 0.75rem 0 0;
  padding-left: 1.25rem;
}

.editor-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
}

.editor-grid {
  margin-top: 0.75rem;
  display: grid;
  grid-template-columns: 320px 1fr;
  gap: 0.75rem;
}

.file-list {
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 10px;
  overflow: hidden;
  max-height: 520px;
  overflow-y: auto;
}

.file-item {
  width: 100%;
  text-align: left;
  padding: 0.6rem 0.75rem;
  background: transparent;
  border: 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  color: inherit;
  cursor: pointer;
}

.file-item.active {
  background: rgba(76, 175, 80, 0.12);
}

.file-editor {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.file-editor-header {
  opacity: 0.9;
}

textarea.code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
  white-space: pre;
}

@media (max-width: 900px) {
  .grid {
    grid-template-columns: 1fr;
  }

  .stepper {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .editor-grid {
    grid-template-columns: 1fr;
  }
}
</style>
