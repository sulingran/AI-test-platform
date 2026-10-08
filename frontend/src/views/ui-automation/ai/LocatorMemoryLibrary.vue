<template>
  <div class="page-container">
    <div class="page-header">
      <h1 class="page-title">{{ $t('menu.locatorMemory') }}</h1>
      <div class="header-actions">
        <el-input
          v-model="keyword"
          :placeholder="$t('uiAutomation.locatorMemory.searchPlaceholder')"
          clearable
          style="width: 260px"
          @keyup.enter="handleSearch"
          @clear="handleSearch"
        >
          <template #append>
            <el-button @click="handleSearch">
              <el-icon><Search /></el-icon>
            </el-button>
          </template>
        </el-input>
        <el-button @click="handleReset" style="margin-left: 10px">
          <el-icon><Refresh /></el-icon>
          {{ $t('uiAutomation.common.reset') }}
        </el-button>
      </div>
    </div>

    <div class="card-container">
      <el-table :data="records" v-loading="loading" style="width: 100%">
        <el-table-column :label="$t('uiAutomation.locatorMemory.serialNumber')" width="70">
          <template #default="{ $index }">
            {{ getSerialNumber($index) }}
          </template>
        </el-table-column>
        <el-table-column prop="page_url" :label="$t('uiAutomation.locatorMemory.pageUrl')" min-width="220" show-overflow-tooltip />
        <el-table-column prop="semantic_text" :label="$t('uiAutomation.locatorMemory.semanticText')" min-width="200" show-overflow-tooltip />
        <el-table-column prop="node_name" :label="$t('uiAutomation.locatorMemory.nodeName')" width="120" />
        <el-table-column prop="locator_strategy" :label="$t('uiAutomation.locatorMemory.locatorStrategy')" width="130" />
        <el-table-column prop="locator_value" :label="$t('uiAutomation.locatorMemory.locatorValue')" min-width="180" show-overflow-tooltip />
        <el-table-column prop="hit_count" :label="$t('uiAutomation.locatorMemory.hitCount')" width="100" align="center" />
        <el-table-column prop="is_valid" :label="$t('uiAutomation.locatorMemory.isValid')" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="row.is_valid ? 'success' : 'danger'" size="small">
              {{ row.is_valid ? $t('uiAutomation.locatorMemory.valid') : $t('uiAutomation.locatorMemory.invalid') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="last_hit_at" :label="$t('uiAutomation.locatorMemory.lastHitAt')" width="180" :formatter="formatDate" />
        <el-table-column prop="updated_at" :label="$t('uiAutomation.locatorMemory.updatedAt')" width="180" :formatter="formatDate" />
        <el-table-column :label="$t('uiAutomation.common.operation')" width="100" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="viewDetail(row)">
              {{ $t('uiAutomation.locatorMemory.viewDetail') }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-container">
        <el-pagination
          v-model:current-page="pagination.currentPage"
          v-model:page-size="pagination.pageSize"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          :total="total"
          @size-change="handleSizeChange"
          @current-change="handleCurrentChange"
        />
      </div>
    </div>

    <!-- 详情对话框 -->
    <el-dialog v-model="showDetailDialog" :title="$t('uiAutomation.locatorMemory.detailTitle')" width="720px">
      <div v-if="currentRecord" class="memory-detail">
        <div class="detail-item">
          <span class="label">{{ $t('uiAutomation.locatorMemory.pageUrl') }}:</span>
          <span class="value">{{ currentRecord.page_url }}</span>
        </div>
        <div class="detail-item">
          <span class="label">{{ $t('uiAutomation.locatorMemory.projectName') }}:</span>
          <span class="value">{{ currentRecord.project_name || '-' }}</span>
        </div>
        <div class="detail-item">
          <span class="label">{{ $t('uiAutomation.locatorMemory.sourceRecord') }}:</span>
          <span class="value">{{ currentRecord.source_record_name || '-' }}</span>
        </div>
        <div class="detail-item">
          <span class="label">{{ $t('uiAutomation.locatorMemory.semanticText') }}:</span>
          <span class="value">{{ currentRecord.semantic_text }}</span>
        </div>
        <div class="detail-item">
          <span class="label">{{ $t('uiAutomation.locatorMemory.nodeName') }}:</span>
          <span class="value">{{ currentRecord.node_name }}</span>
        </div>
        <div class="detail-item">
          <span class="label">{{ $t('uiAutomation.locatorMemory.locatorStrategy') }}:</span>
          <span class="value">{{ currentRecord.locator_strategy }}</span>
        </div>
        <div class="detail-item">
          <span class="label">{{ $t('uiAutomation.locatorMemory.locatorValue') }}:</span>
          <span class="value">{{ currentRecord.locator_value }}</span>
        </div>
        <div class="detail-item">
          <span class="label">{{ $t('uiAutomation.locatorMemory.confidence') }}:</span>
          <span class="value">{{ currentRecord.confidence }}</span>
        </div>
        <div class="detail-item">
          <span class="label">{{ $t('uiAutomation.locatorMemory.semanticKey') }}:</span>
          <span class="value">{{ currentRecord.semantic_key }}</span>
        </div>

        <div class="detail-item mt-15">
          <span class="label">{{ $t('uiAutomation.locatorMemory.attributes') }}:</span>
        </div>
        <div class="json-container">
          <pre>{{ formatJson(currentRecord.attributes) }}</pre>
        </div>

        <div class="detail-item mt-15">
          <span class="label">{{ $t('uiAutomation.locatorMemory.embedding') }}:</span>
        </div>
        <div class="json-container">
          <pre>{{ formatJson(currentRecord.embedding) }}</pre>
        </div>
      </div>

      <template #footer>
        <div class="dialog-footer">
          <el-button @click="showDetailDialog = false">{{ $t('uiAutomation.common.close') }}</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Search, Refresh } from '@element-plus/icons-vue'
import { getLocatorMemories } from '@/api/ui_automation'

const records = ref([])
const loading = ref(false)
const total = ref(0)
const keyword = ref('')
const pagination = reactive({
  currentPage: 1,
  pageSize: 20
})

const showDetailDialog = ref(false)
const currentRecord = ref(null)

const loadRecords = async () => {
  loading.value = true
  try {
    const params = {
      page: pagination.currentPage,
      page_size: pagination.pageSize
    }
    if (keyword.value) {
      params.search = keyword.value
    }
    const response = await getLocatorMemories(params)
    records.value = response.data.results || []
    total.value = response.data.count || 0
  } catch (error) {
    console.error('获取定位器记忆库失败:', error)
    ElMessage.error('获取定位器记忆库失败')
  } finally {
    loading.value = false
  }
}

const handleSearch = () => {
  pagination.currentPage = 1
  loadRecords()
}

const handleReset = () => {
  keyword.value = ''
  pagination.currentPage = 1
  loadRecords()
}

const handleSizeChange = () => {
  pagination.currentPage = 1
  loadRecords()
}

const handleCurrentChange = () => {
  loadRecords()
}

const viewDetail = (row) => {
  currentRecord.value = row
  showDetailDialog.value = true
}

const getSerialNumber = (index) => {
  return (pagination.currentPage - 1) * pagination.pageSize + index + 1
}

const formatDate = (row, column, cellValue) => {
  if (!cellValue) return '-'
  return new Date(cellValue).toLocaleString()
}

const formatJson = (value) => {
  if (value === null || value === undefined) return '-'
  try {
    return JSON.stringify(value, null, 2)
  } catch (e) {
    return String(value)
  }
}

onMounted(() => {
  loadRecords()
})
</script>

<style lang="scss" scoped>
.page-container {
  padding: 20px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;

  .page-title {
    font-size: 20px;
    font-weight: 600;
    margin: 0;
  }

  .header-actions {
    display: flex;
    align-items: center;
  }
}

.card-container {
  background-color: #fff;
  border-radius: 4px;
  padding: 20px;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.1);
}

.pagination-container {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}

.memory-detail {
  .detail-item {
    margin-bottom: 15px;
    .label {
      font-weight: bold;
      margin-right: 10px;
    }
    .value {
      word-break: break-all;
    }
  }

  .json-container {
    background-color: #f5f7fa;
    border: 1px solid #e4e7ed;
    border-radius: 4px;
    padding: 12px 15px;
    max-height: 300px;
    overflow-y: auto;

    pre {
      margin: 0;
      white-space: pre-wrap;
      word-wrap: break-word;
      font-family: monospace;
      font-size: 12px;
      color: #606266;
    }
  }
}

.mt-15 {
  margin-top: 15px;
}
</style>