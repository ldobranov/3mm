// Public presentation contract. Do not export Core stores/router/API clients here.
import '../assets/ui-platform.css'
export const UI_CONTRACT_VERSION = 1 as const
export { default as UiSurface } from './UiSurface.vue'
export { default as UiButton } from '../components/ui/UiButton.vue'
export { default as UiDialog } from '../components/ui/UiDialog.vue'
export { default as UiField } from './UiField.vue'
export { default as UiForm } from './UiForm.vue'
export { default as UiState } from './UiState.vue'
export { default as UiTable } from './UiTable.vue'
export { default as UiEditorForm } from './UiEditorForm.vue'
export { default as UiRecordPicker } from './UiRecordPicker.vue'
export { default as UiCollectionEditor } from './UiCollectionEditor.vue'
