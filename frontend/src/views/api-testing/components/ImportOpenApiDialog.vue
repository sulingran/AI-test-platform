<template>
  <el-dialog
    v-model="visible"
    :title="$t('apiTesting.importOpenApi.title')"
    width="min(920px, 94vw)"
    :close-on-click-modal="false"
    @closed="reset"
  >
    <div class="openapi-import">
      <el-tabs v-if="!parseResult" v-model="inputMethod" type="border-card">
        <el-tab-pane :label="$t('apiTesting.importOpenApi.uploadFile')" name="file">
          <el-upload
            drag
            action="#"
            :auto-upload="false"
            :limit="1"
            accept=".json,.yaml,.yml"
            :show-file-list="false"
            :on-change="handleFileChange"
          >
            <el-icon class="upload-icon"><UploadFilled /></el-icon>
            <div>{{ $t('apiTesting.importOpenApi.dragOrClick') }}</div>
            <div class="upload-hint">JSON / YAML, {{ $t('apiTesting.importOpenApi.maxFileSize') }}</div>
          </el-upload>
          <div v-if="uploadedFile" class="file-row">
            <el-icon><Document /></el-icon>
            <span class="file-name">{{ uploadedFile.name }}</span>
            <span class="muted">{{ formatFileSize(uploadedFile.size) }}</span>
            <el-button link type="danger" :icon="Delete" @click="uploadedFile = null" />
          </div>
        </el-tab-pane>
        <el-tab-pane :label="$t('apiTesting.importOpenApi.pasteText')" name="paste">
          <el-input
            v-model="pasteContent"
            type="textarea"
            :rows="11"
            :placeholder="$t('apiTesting.importOpenApi.pastePlaceholder')"
          />
        </el-tab-pane>
      </el-tabs>

      <div class="form-row">
        <span class="field-label">{{ $t('apiTesting.importOpenApi.targetProject') }}</span>
        <el-select v-model="projectId" :placeholder="$t('apiTesting.importOpenApi.selectProject')" class="project-select">
          <el-option
            v-for="project in httpProjects"
            :key="project.id"
            :label="project.name"
            :value="project.id"
          />
        </el-select>
      </div>

      <template v-if="parseResult">
        <el-alert type="success" :closable="false" show-icon>
          <template #title>
            {{ parseResult.title }} · {{ parseResult.spec_version }} · {{ parseResult.endpoint_count }}
            {{ $t('apiTesting.importOpenApi.endpoints') }}
          </template>
        </el-alert>

        <div class="selection-bar">
          <el-checkbox v-model="allSelected">{{ $t('apiTesting.importOpenApi.selectAll') }}</el-checkbox>
          <span class="muted">
            {{ $t('apiTesting.importOpenApi.selectedCount', { count: selectedKeys.length }) }}
          </span>
        </div>

        <el-checkbox-group v-model="selectedKeys" class="endpoint-groups">
          <section v-for="group in parseResult.groups" :key="group.tag" class="endpoint-group">
            <header class="group-header">
              <el-icon><Folder /></el-icon>
              <span>{{ group.tag }}</span>
              <span class="muted">({{ group.endpoints.length }})</span>
            </header>
            <div class="endpoint-list">
              <label v-for="endpoint in group.endpoints" :key="endpoint.key" class="endpoint-row">
                <el-checkbox :value="endpoint.key" />
                <el-tag size="small" :type="methodTagType(endpoint.method)" class="method-tag">
                  {{ endpoint.method }}
                </el-tag>
                <code class="endpoint-path">{{ endpoint.path }}</code>
                <span class="endpoint-summary">{{ endpoint.summary || endpoint.operation_id || endpoint.path }}</span>
                <span class="endpoint-flags">
                  <el-tag v-if="hasParameter(endpoint, 'path')" size="small" effect="plain">Path</el-tag>
                  <el-tag v-if="hasParameter(endpoint, 'query')" size="small" effect="plain">Query</el-tag>
                  <el-tag v-if="endpoint.request_body" size="small" effect="plain">Body</el-tag>
                  <el-tag v-if="endpoint.auth_headers?.length" size="small" type="warning" effect="plain">Auth</el-tag>
                </span>
              </label>
            </div>
          </section>
        </el-checkbox-group>

        <div class="import-options">
          <div class="form-row">
            <span class="field-label">Base URL</span>
            <el-input v-model="baseUrl" placeholder="https://api.example.com" />
          </div>
          <div class="form-row">
            <span class="field-label">{{ $t('apiTesting.importOpenApi.duplicateStrategy') }}</span>
            <el-radio-group v-model="duplicateStrategy" size="small">
              <el-radio-button value="skip">{{ $t('apiTesting.importOpenApi.skipDuplicates') }}</el-radio-button>
              <el-radio-button value="update">{{ $t('apiTesting.importOpenApi.updateDuplicates') }}</el-radio-button>
            </el-radio-group>
          </div>
          <el-checkbox v-model="byTag">{{ $t('apiTesting.importOpenApi.byTag') }}</el-checkbox>
          <el-alert
            v-if="duplicateStrategy === 'update'"
            type="warning"
            :closable="false"
            :title="$t('apiTesting.importOpenApi.updateWarning')"
            show-icon
          />
        </div>
      </template>
    </div>

    <template #footer>
      <el-button @click="visible = false">{{ $t('apiTesting.common.cancel') }}</el-button>
      <el-button
        v-if="!parseResult"
        type="primary"
        :loading="parsing"
        :disabled="!canParse"
        @click="parseDocument"
      >
        {{ $t('apiTesting.importOpenApi.parse') }}
      </el-button>
      <el-button
        v-else
        type="primary"
        :loading="importing"
        :disabled="selectedKeys.length === 0"
        @click="importDocument"
      >
        {{ $t('apiTesting.importOpenApi.import') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { Delete, Document, Folder, UploadFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'
import api from '@/utils/api'

const props = defineProps({
  modelValue: Boolean,
  projects: { type: Array, default: () => [] },
  initialProjectId: { type: [Number, String], default: null },
})
const emit = defineEmits(['update:modelValue', 'imported'])
const { t } = useI18n()

const visible = computed({
  get: () => props.modelValue,
  set: value => emit('update:modelValue', value),
})
const httpProjects = computed(() => props.projects.filter(project => project.project_type === 'HTTP'))
const inputMethod = ref('file')
const uploadedFile = ref(null)
const pasteContent = ref('')
const projectId = ref(null)
const baseUrl = ref('')
const parsing = ref(false)
const importing = ref(false)
const parseResult = ref(null)
const documentId = ref(null)
const selectedKeys = ref([])
const byTag = ref(true)
const duplicateStrategy = ref('skip')

const allEndpointKeys = computed(() => (
  parseResult.value?.endpoints?.map(endpoint => endpoint.key) || []
))
const allSelected = computed({
  get: () => allEndpointKeys.value.length > 0 && selectedKeys.value.length === allEndpointKeys.value.length,
  set: value => { selectedKeys.value = value ? [...allEndpointKeys.value] : [] },
})
const canParse = computed(() => {
  const hasInput = inputMethod.value === 'file' ? uploadedFile.value : pasteContent.value.trim()
  return Boolean(projectId.value && hasInput)
})

function handleFileChange(file) {
  if (file.raw.size > 5 * 1024 * 1024) {
    ElMessage.warning(t('apiTesting.importOpenApi.fileTooLarge'))
    uploadedFile.value = null
    return
  }
  uploadedFile.value = file.raw
}

function formatFileSize(bytes) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function methodTagType(method) {
  return ({ GET: 'success', POST: 'primary', PUT: 'warning', DELETE: 'danger', PATCH: 'info' })[method] || 'info'
}

function hasParameter(endpoint, location) {
  return endpoint.parameters?.some(parameter => parameter.in === location)
}

function errorMessage(error) {
  const data = error.response?.data
  if (typeof data?.error === 'string') return data.error
  if (data && typeof data === 'object') {
    const first = Object.values(data).flat()[0]
    if (first) return String(first)
  }
  return error.message || t('apiTesting.importOpenApi.importFailed')
}

async function parseDocument() {
  parsing.value = true
  try {
    const formData = new FormData()
    if (inputMethod.value === 'file') {
      formData.append('title', uploadedFile.value.name.replace(/\.(json|ya?ml)$/i, ''))
      formData.append('file', uploadedFile.value)
    } else {
      const isJson = pasteContent.value.trim().startsWith('{')
      const fileName = isJson ? 'openapi.json' : 'openapi.yaml'
      formData.append('title', 'OpenAPI')
      formData.append('file', new Blob([pasteContent.value], { type: 'text/plain' }), fileName)
    }
    formData.append('project', projectId.value)
    const upload = await api.post('/api-testing/api-docs/', formData)
    documentId.value = upload.data.id
    const parsed = await api.post(`/api-testing/api-docs/${documentId.value}/parse/`)
    parseResult.value = parsed.data
    baseUrl.value = parsed.data.base_url || ''
    selectedKeys.value = parsed.data.endpoints.map(endpoint => endpoint.key)
    ElMessage.success(t('apiTesting.importOpenApi.parseSuccess'))
  } catch (error) {
    ElMessage.error(`${t('apiTesting.importOpenApi.parseFailed')}: ${errorMessage(error)}`)
  } finally {
    parsing.value = false
  }
}

async function importDocument() {
  importing.value = true
  try {
    const response = await api.post(`/api-testing/api-docs/${documentId.value}/import/`, {
      project_id: projectId.value,
      endpoint_keys: selectedKeys.value,
      base_url: baseUrl.value,
      by_tag: byTag.value,
      duplicate_strategy: duplicateStrategy.value,
    })
    const result = response.data
    ElMessage.success(t('apiTesting.importOpenApi.result', {
      created: result.created_count,
      updated: result.updated_count,
      skipped: result.skipped_count,
    }))
    emit('imported', result)
    visible.value = false
  } catch (error) {
    ElMessage.error(`${t('apiTesting.importOpenApi.importFailed')}: ${errorMessage(error)}`)
  } finally {
    importing.value = false
  }
}

function reset() {
  inputMethod.value = 'file'
  uploadedFile.value = null
  pasteContent.value = ''
  parseResult.value = null
  documentId.value = null
  selectedKeys.value = []
  baseUrl.value = ''
  byTag.value = true
  duplicateStrategy.value = 'skip'
  projectId.value = props.initialProjectId || null
}

watch(() => props.modelValue, value => {
  if (value) projectId.value = props.initialProjectId || httpProjects.value[0]?.id || null
})
</script>

<style scoped>
.openapi-import { display: flex; flex-direction: column; gap: 16px; }
.upload-icon { font-size: 42px; color: var(--el-color-primary); }
.upload-hint, .muted { color: var(--el-text-color-secondary); font-size: 12px; }
.file-row { display: flex; align-items: center; gap: 8px; margin-top: 10px; }
.file-name { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.form-row { display: grid; grid-template-columns: 110px minmax(0, 1fr); align-items: center; gap: 12px; }
.field-label { font-size: 13px; font-weight: 500; }
.project-select { width: min(360px, 100%); }
.selection-bar { display: flex; align-items: center; justify-content: space-between; }
.endpoint-groups { max-height: 390px; overflow-y: auto; border: 1px solid var(--el-border-color); }
.endpoint-group + .endpoint-group { border-top: 1px solid var(--el-border-color); }
.group-header { display: flex; align-items: center; gap: 6px; padding: 8px 12px; background: var(--el-fill-color-light); font-size: 13px; font-weight: 600; }
.endpoint-list { display: flex; flex-direction: column; }
.endpoint-row { display: grid; grid-template-columns: 28px 66px minmax(170px, 1.2fr) minmax(130px, 1fr) auto; align-items: center; gap: 8px; min-height: 42px; padding: 5px 12px; border-top: 1px solid var(--el-border-color-lighter); cursor: pointer; }
.endpoint-row:hover { background: var(--el-fill-color-lighter); }
.method-tag { width: 62px; justify-content: center; }
.endpoint-path, .endpoint-summary { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.endpoint-path { font-size: 12px; }
.endpoint-summary { font-size: 13px; }
.endpoint-flags { display: flex; gap: 4px; }
.import-options { display: flex; flex-direction: column; gap: 12px; }
@media (max-width: 720px) {
  .form-row { grid-template-columns: 1fr; gap: 6px; }
  .endpoint-row { grid-template-columns: 24px 64px minmax(120px, 1fr); }
  .endpoint-summary, .endpoint-flags { display: none; }
}
</style>
