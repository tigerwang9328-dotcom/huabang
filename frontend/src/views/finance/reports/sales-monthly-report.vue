<template>
  <div class="smr-page">
    <!-- 顶部工具栏 -->
    <div class="smr-toolbar">
      <div class="toolbar-left">
        <el-button plain @click="ownershipDrawerVisible = true">
          <el-icon><Setting /></el-icon> 店铺归属配置
        </el-button>
        <el-date-picker
          v-model="filterMonth"
          type="month"
          value-format="YYYY-MM"
          placeholder="按月份筛选"
          clearable
          style="width:140px"
          @change="loadBatches"
        />
        <el-select
          v-model="filterScopeType"
          placeholder="全部范围"
          clearable
          style="width:130px"
          @change="loadBatches"
        >
          <el-option label="全部店铺" value="all_stores" />
          <el-option label="按合伙人" value="partner" />
          <el-option label="自定义分组" value="custom_group" />
          <el-option label="单店铺" value="single_store" />
        </el-select>
      </div>
      <div class="toolbar-right">
        <el-button type="primary" @click="openCreateBatch">
          <el-icon><Plus /></el-icon> 新建批次
        </el-button>
      </div>
    </div>

    <!-- 批次列表 -->
    <el-table
      :data="batches"
      v-loading="batchLoading"
      border
      highlight-current-row
      @current-change="onBatchSelect"
      style="margin-bottom:16px"
    >
      <el-table-column prop="month" label="月份" width="90" />
      <el-table-column prop="batch_name" label="批次名称" min-width="180" show-overflow-tooltip />
      <el-table-column label="范围" width="110">
        <template #default="{ row }">
          <span>{{ scopeTypeLabel(row.scope_type) }}</span>
          <span v-if="row.scope_name" class="scope-name">{{ row.scope_name }}</span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag :type="statusTagType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="店铺/预期" width="100" align="center">
        <template #default="{ row }">
          {{ row.store_count }}<span v-if="row.expected_store_count" class="text-muted">/{{ row.expected_store_count }}</span>
        </template>
      </el-table-column>
      <el-table-column label="文件" width="70" align="center" prop="uploaded_file_count" />
      <el-table-column label="缺必传" width="80" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.missing_required_count > 0" type="danger" size="small">{{ row.missing_required_count }}</el-tag>
          <span v-else class="text-muted">-</span>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建时间" width="150" :formatter="fmtTime" />
      <el-table-column label="操作" width="160" fixed="right">
        <template #default="{ row }">
          <el-button type="primary" link size="small" @click.stop="onBatchSelect(row)">详情</el-button>
          <el-button v-if="row.status === 'completed'" type="warning" link size="small" @click.stop="doLock(row)">锁定</el-button>
          <el-button type="danger" link size="small" @click.stop="doDeleteBatch(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 批次详情 -->
    <div v-if="currentBatch" class="batch-detail">
      <div class="detail-header">
        <span class="detail-title">
          {{ currentBatch.batch_name }}
          <el-tag :type="statusTagType(currentBatch.status)" size="small" style="margin-left:8px">
            {{ statusLabel(currentBatch.status) }}
          </el-tag>
        </span>
        <el-button size="small" plain @click="currentBatch = null">收起</el-button>
      </div>

      <el-tabs v-model="activeTab" class="detail-tabs">

        <!-- ── Tab1: 文件上传 ───────────────────────────── -->
        <el-tab-pane label="文件上传" name="upload">
          <div class="upload-mode-bar">
            <el-radio-group v-model="uploadMode" size="small">
              <el-radio-button value="single">单文件上传</el-radio-button>
              <el-radio-button value="bulk">批量上传</el-radio-button>
              <el-radio-button value="matrix">上传进度矩阵</el-radio-button>
              <el-radio-button value="workbook">单店工作簿</el-radio-button>
              <el-radio-button value="bulk_workbook">批量工作簿</el-radio-button>
            </el-radio-group>
            <el-badge v-if="unconfirmedCount > 0" :value="unconfirmedCount" type="danger" style="margin-left:12px">
              <el-button size="small" type="warning" @click="openConfirmDialog">待确认文件</el-button>
            </el-badge>
          </div>

          <!-- 单文件上传 -->
          <div v-if="uploadMode === 'single'" class="single-upload">
            <el-form :model="singleUploadForm" inline label-width="80px">
              <el-form-item label="文件类型">
                <el-select v-model="singleUploadForm.file_type" style="width:150px">
                  <el-option v-for="ft in FILE_TYPE_OPTIONS" :key="ft.value" :label="ft.label" :value="ft.value" />
                </el-select>
              </el-form-item>
              <el-form-item label="店铺名称">
                <el-input v-model="singleUploadForm.store_name" placeholder="请输入店铺名称" style="width:200px" />
              </el-form-item>
            </el-form>
            <el-upload ref="singleUploadRef" drag :auto-upload="false" :on-change="onSingleFileChange"
              :on-remove="onSingleFileRemove" :show-file-list="true" accept=".xlsx,.xlsm,.xls,.csv">
              <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
              <div class="el-upload__text">将文件拖到此处，或<em>点击上传</em></div>
              <template #tip><div class="el-upload__tip">支持 .xlsx / .xlsm / .csv（.xls 建议另存为 .xlsx）</div></template>
            </el-upload>
            <div style="margin-top:12px">
              <el-button type="primary"
                :disabled="isBatchLocked"
                :loading="singleUploading" @click="doSingleUpload">上传</el-button>
              <span v-if="isBatchLocked" class="upload-lock-tip">当前批次已锁定，不能上传</span>
            </div>
          </div>

          <!-- 批量上传 -->
          <div v-else-if="uploadMode === 'bulk'" class="bulk-upload">
            <el-upload drag multiple :auto-upload="false" :on-change="onBulkFileAdd"
              :file-list="[]" :show-file-list="false" accept=".xlsx,.xls,.csv">
              <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
              <div class="el-upload__text">将多个文件拖到此处，或<em>点击选择</em></div>
              <template #tip><div class="el-upload__tip">自动识别文件类型和店铺名称，支持 .xlsx / .xls / .csv</div></template>
            </el-upload>
            <div v-if="bulkFileList.length > 0" style="margin-top:12px">
              <div class="bulk-file-count">已选 {{ bulkFileList.length }} 个文件</div>
              <el-button type="primary" :loading="bulkUploading" @click="doBulkUpload" style="margin-top:8px">开始批量上传</el-button>
              <el-button @click="bulkFileList = []" style="margin-left:8px">清空</el-button>
            </div>
            <div v-if="bulkResult" class="bulk-result">
              <div class="bulk-result-stats">
                <el-tag type="success">识别成功 {{ bulkResult.detected_count }}</el-tag>
                <el-tag type="warning" style="margin:0 8px">待确认 {{ bulkResult.need_confirm_count }}</el-tag>
                <el-tag type="danger">失败 {{ bulkResult.failed_count }}</el-tag>
              </div>
              <el-table :data="bulkResult.results" border size="small" style="margin-top:8px">
                <el-table-column prop="original_filename" label="文件名" min-width="200" show-overflow-tooltip />
                <el-table-column label="识别文件类型" width="130">
                  <template #default="{ row }">{{ row.detected_file_type ? fileTypeLabel(row.detected_file_type) : '-' }}</template>
                </el-table-column>
                <el-table-column prop="detected_store_name" label="识别店铺" width="150" show-overflow-tooltip />
                <el-table-column label="状态" width="100">
                  <template #default="{ row }">
                    <el-tag :type="detectStatusTag(row.detect_status)" size="small">{{ detectStatusLabel(row.detect_status) }}</el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="detect_message" label="说明" min-width="160" show-overflow-tooltip />
              </el-table>
            </div>
          </div>

          <!-- 上传进度矩阵 -->
          <div v-else-if="uploadMode === 'matrix'">
            <div class="matrix-header">
              <el-button size="small" @click="loadMatrix" :loading="matrixLoading"><el-icon><Refresh /></el-icon> 刷新</el-button>
              <template v-if="matrixData">
                <el-tag type="success" style="margin-left:8px">完整 {{ matrixData.complete_count }}</el-tag>
                <el-tag type="danger" style="margin:0 6px">缺必传 {{ matrixData.missing_required_count }}</el-tag>
                <el-tag type="warning">缺可选 {{ matrixData.missing_optional_count }}</el-tag>
              </template>
            </div>
            <el-table v-if="matrixData && matrixData.rows.length > 0" :data="matrixData.rows"
              border size="small" v-loading="matrixLoading" style="margin-top:8px">
              <el-table-column prop="store_name" label="店铺" width="150" fixed="left" show-overflow-tooltip />
              <el-table-column prop="partner_name" label="合伙人" width="100" show-overflow-tooltip />
              <el-table-column v-for="ft in ALL_FILE_TYPES" :key="ft.value" :label="ft.label" :width="ft.required ? 100 : 90" align="center">
                <template #header>
                  <span>{{ ft.label }}</span><el-tag v-if="ft.required" type="danger" size="small" style="margin-left:2px">必</el-tag>
                </template>
                <template #default="{ row }">
                  <span :class="matrixCellClass(row.files[ft.value])">{{ matrixCellText(row.files[ft.value]) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="状态" width="110" fixed="right">
                <template #default="{ row }">
                  <el-tag :type="storeMatrixStatusTag(row.status)" size="small">{{ storeMatrixStatusLabel(row.status) }}</el-tag>
                </template>
              </el-table-column>
            </el-table>
            <el-empty v-else-if="matrixData && matrixData.rows.length === 0" description="暂无店铺数据，请先配置店铺归属" />
          </div>

          <!-- 单店工作簿上传 -->
          <div v-else-if="uploadMode === 'workbook'">
            <el-form label-width="100px" style="max-width:600px">
              <el-form-item label="店铺名称" required>
                <el-input v-model="wbStoreName" placeholder="请输入店铺名称" clearable />
                <div v-if="currentBatch?.scope_type === 'single_store'" style="color:#909399;font-size:12px;margin-top:4px">
                  当前批次为单店铺，已自动填入
                </div>
              </el-form-item>
              <el-form-item label="工作簿文件" required>
                <el-button @click="wbFileInput?.click()">选择工作簿 (.xlsx)</el-button>
                <span v-if="wbFile" style="margin-left:8px;color:#409EFF">{{ wbFile.name }}</span>
                <input ref="wbFileInput" type="file" accept=".xlsx,.xlsm,.xltx,.xltm" style="display:none" @change="onWbFileChange" />
                <div class="el-upload__tip" style="margin-top:4px">工作簿上传只支持 .xlsx 文件，CSV 请使用单表上传</div>
              </el-form-item>
              <el-form-item>
                <el-button type="primary" :loading="wbUploading" @click="doUploadWorkbook">上传工作簿</el-button>
              </el-form-item>
            </el-form>

            <!-- 解析结果 -->
            <div v-if="wbResult" style="margin-top:16px">
              <div style="margin-bottom:8px;font-weight:600">
                工作簿解析结果：{{ wbResult.original_filename }}
                <el-tag type="success" style="margin-left:8px">识别 {{ wbResult.detected_count }}</el-tag>
                <el-tag v-if="wbResult.need_confirm_count" type="warning" style="margin-left:4px">待确认 {{ wbResult.need_confirm_count }}</el-tag>
                <el-tag v-if="wbResult.failed_count" type="danger" style="margin-left:4px">失败 {{ wbResult.failed_count }}</el-tag>
                <el-tag v-if="wbResult.skipped_count" type="info" style="margin-left:4px">跳过 {{ wbResult.skipped_count }}</el-tag>
              </div>
              <el-table :data="wbResult.sheet_results" border size="small">
                <el-table-column prop="sheet_name" label="Sheet名称" width="160" />
                <el-table-column label="识别类型" width="130">
                  <template #default="{ row }">
                    <span>{{ row.detected_file_type ? fileTypeLabel(row.detected_file_type) : '-' }}</span>
                  </template>
                </el-table-column>
                <el-table-column prop="row_count" label="行数" width="80" />
                <el-table-column label="状态" width="100">
                  <template #default="{ row }">
                    <el-tag :type="sheetStatusType(row.detect_status)" size="small">{{ sheetStatusLabel(row.detect_status) }}</el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="error_message" label="说明" show-overflow-tooltip />
              </el-table>
            </div>
          </div>

          <!-- 批量工作簿上传 -->
          <div v-else-if="uploadMode === 'bulk_workbook'">
            <el-form label-width="100px" style="max-width:600px">
              <el-form-item label="工作簿文件" required>
                <el-button @click="bulkWbFileInput?.click()">选择多个工作簿</el-button>
                <span v-if="bulkWbFiles.length" style="margin-left:8px;color:#409EFF">已选 {{ bulkWbFiles.length }} 个文件</span>
                <input ref="bulkWbFileInput" type="file" accept=".xlsx,.xlsm,.xltx,.xltm" multiple style="display:none" @change="onBulkWbFileChange" />
              </el-form-item>
              <el-form-item>
                <el-button type="primary" :loading="bulkWbUploading" @click="doBulkUploadWorkbooks">批量上传</el-button>
              </el-form-item>
            </el-form>
            <div style="color:#909399;font-size:12px;margin-bottom:12px">
              文件名需包含店铺归属配置中的店铺名称，系统自动识别；无法识别的进入待确认。
            </div>

            <!-- 批量结果 -->
            <div v-for="(result, idx) in bulkWbResults" :key="idx" style="margin-bottom:20px">
              <div style="margin-bottom:8px;font-weight:600">
                {{ result.original_filename }}（{{ result.store_name || '店铺未识别' }}）
                <el-tag type="success" style="margin-left:8px">识别 {{ result.detected_count }}</el-tag>
                <el-tag v-if="result.need_confirm_count" type="warning" style="margin-left:4px">待确认 {{ result.need_confirm_count }}</el-tag>
                <el-tag v-if="result.failed_count" type="danger" style="margin-left:4px">失败 {{ result.failed_count }}</el-tag>
              </div>
              <el-table v-if="result.sheet_results.length" :data="result.sheet_results" border size="small">
                <el-table-column prop="sheet_name" label="Sheet名称" width="160" />
                <el-table-column label="识别类型" width="130">
                  <template #default="{ row }">{{ row.detected_file_type ? fileTypeLabel(row.detected_file_type) : '-' }}</template>
                </el-table-column>
                <el-table-column prop="row_count" label="行数" width="80" />
                <el-table-column label="状态" width="100">
                  <template #default="{ row }">
                    <el-tag :type="sheetStatusType(row.detect_status)" size="small">{{ sheetStatusLabel(row.detect_status) }}</el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="error_message" label="说明" show-overflow-tooltip />
              </el-table>
              <el-alert v-else type="warning" :title="`无法识别店铺或工作簿解析失败：${result.original_filename}`" show-icon />
            </div>
          </div>
        </el-tab-pane>

        <!-- ── Tab2: 简版看板 ──────────────────────────── -->
        <el-tab-pane label="简版看板" name="simple">
          <div class="report-toolbar">
            <el-button type="primary" :loading="generating" :disabled="currentBatch.status === 'locked'" @click="openGenerateDialog">
              <el-icon><Lightning /></el-icon> 生成月报
            </el-button>
            <template v-if="reportData">
              <el-button @click="doExportReport">导出完整月报</el-button>
              <el-button @click="doExport('pending')">导出待结算</el-button>
              <el-button @click="doExport('abnormal')">导出异常</el-button>
            </template>
          </div>
          <div v-if="reportData">
            <!-- KPI 卡片 -->
            <div class="kpi-cards">
              <div class="kpi-card">
                <div class="kpi-label">店铺数</div>
                <div class="kpi-value">{{ reportData.summary.store_count }}</div>
              </div>
              <div class="kpi-card">
                <div class="kpi-label">发货单量</div>
                <div class="kpi-value">{{ reportData.summary.shipped_order_count }}</div>
              </div>
              <div class="kpi-card">
                <div class="kpi-label">实际销售额</div>
                <div class="kpi-value kpi-primary">¥{{ fmtAmount(reportData.summary.actual_sales_amount) }}</div>
              </div>
              <div class="kpi-card">
                <div class="kpi-label">净利润</div>
                <div :class="['kpi-value', parseFloat(reportData.summary.net_profit) >= 0 ? 'kpi-profit' : 'kpi-loss']">
                  ¥{{ fmtAmount(reportData.summary.net_profit) }}
                </div>
              </div>
              <div class="kpi-card">
                <div class="kpi-label">待结算</div>
                <div class="kpi-value kpi-warn">{{ reportData.summary.pending_settlement_count }}</div>
              </div>
              <div class="kpi-card">
                <div class="kpi-label">异常单</div>
                <div class="kpi-value kpi-danger">{{ reportData.summary.abnormal_count }}</div>
              </div>
            </div>

            <!-- 简版表格 -->
            <el-table :data="reportData.shops" border size="small" show-summary :summary-method="simpleTableSummary">
              <el-table-column prop="store_name" label="店铺" width="140" fixed="left" show-overflow-tooltip />
              <el-table-column prop="shipped_order_count" label="发货订单" width="85" align="right" />
              <el-table-column label="发货金额" width="110" align="right">
                <template #default="{ row }">¥{{ fmtAmount(row.shipped_amount) }}</template>
              </el-table-column>
              <el-table-column label="实际销售额" width="120" align="right">
                <template #default="{ row }">¥{{ fmtAmount(row.actual_sales_amount) }}</template>
              </el-table-column>
              <el-table-column prop="actual_sales_order_count" label="实销单量" width="85" align="right" />
              <el-table-column label="客单价" width="100" align="right">
                <template #default="{ row }">¥{{ fmtAmount(row.avg_order_amount) }}</template>
              </el-table-column>
              <el-table-column prop="refund_order_count" label="退款订单" width="85" align="right" />
              <el-table-column label="商品成本" width="110" align="right">
                <template #default="{ row }">¥{{ fmtAmount(row.actual_product_cost) }}</template>
              </el-table-column>
              <el-table-column label="净利润" width="110" align="right">
                <template #default="{ row }">
                  <span :class="parseFloat(row.net_profit) >= 0 ? 'text-profit' : 'text-loss'">
                    ¥{{ fmtAmount(row.net_profit) }}
                  </span>
                </template>
              </el-table-column>
              <el-table-column label="净利润率" width="90" align="right">
                <template #default="{ row }">{{ fmtRate(row.net_profit_rate) }}%</template>
              </el-table-column>
            </el-table>
          </div>
          <el-empty v-else description="请先生成月报" />
        </el-tab-pane>

        <!-- ── Tab3: 完整月报 ──────────────────────────── -->
        <el-tab-pane label="完整月报" name="full">
          <div class="report-toolbar">
            <el-button type="primary" :loading="generating" :disabled="currentBatch.status === 'locked'" @click="openGenerateDialog">
              <el-icon><Lightning /></el-icon> 生成月报
            </el-button>
            <el-button v-if="reportData" type="success" @click="doExportReport">
              <el-icon><Download /></el-icon> 导出完整月报Excel
            </el-button>
          </div>

          <div v-if="reportData" class="full-report-wrap">
            <el-table
              :data="reportData.shops"
              border
              size="small"
              height="500"
              show-summary
              :summary-method="fullTableSummary"
            >
              <!-- 固定列 -->
              <el-table-column label="序号" type="index" width="55" fixed="left" align="center" />
              <el-table-column prop="store_code" label="店铺编号" width="110" fixed="left" show-overflow-tooltip>
                <template #default="{ row }">{{ row.store_code || '-' }}</template>
              </el-table-column>
              <el-table-column prop="store_name" label="店铺" width="150" fixed="left" show-overflow-tooltip />
              <!-- 发货 / 退款 -->
              <el-table-column prop="shipped_order_count" label="发货订单数" width="100" align="right" />
              <el-table-column label="发货金额" width="110" align="right">
                <template #default="{ row }">{{ fmtAmt(row.shipped_amount) }}</template>
              </el-table-column>
              <el-table-column prop="refund_order_count" label="退款订单数" width="100" align="right" />
              <el-table-column label="发货后退款金额" width="130" align="right">
                <template #default="{ row }">{{ fmtAmt(row.after_ship_refund_amount) }}</template>
              </el-table-column>
              <el-table-column label="发货前退款金额" width="130" align="right">
                <template #default="{ row }">{{ fmtAmt(row.before_ship_refund_amount) }}</template>
              </el-table-column>
              <el-table-column label="结算后退款金额" width="130" align="right">
                <template #default="{ row }">{{ fmtAmt(row.after_settlement_refund_amount) }}</template>
              </el-table-column>
              <!-- 销售 -->
              <el-table-column label="实际销售额" width="120" align="right">
                <template #default="{ row }">{{ fmtAmt(row.actual_sales_amount) }}</template>
              </el-table-column>
              <el-table-column prop="actual_sales_order_count" label="实销单量" width="90" align="right" />
              <el-table-column prop="actual_sales_order_completed" label="实际销售订单" width="110" align="right" />
              <el-table-column label="已付款销售额" width="120" align="right">
                <template #default="{ row }">{{ fmtAmt(row.paid_sales_amount) }}</template>
              </el-table-column>
              <el-table-column label="客单价" width="100" align="right">
                <template #default="{ row }">{{ fmtAmt(row.avg_order_amount) }}</template>
              </el-table-column>
              <!-- 成本/费用 -->
              <el-table-column label="实际销售成本" width="120" align="right">
                <template #default="{ row }">{{ fmtAmt(row.actual_product_cost) }}</template>
              </el-table-column>
              <el-table-column label="平台服务费" width="110" align="right">
                <template #default="{ row }">{{ fmtAmt(row.platform_service_fee) }}</template>
              </el-table-column>
              <el-table-column label="达人佣金" width="100" align="right">
                <template #default="{ row }">{{ fmtAmt(row.talent_commission) }}</template>
              </el-table-column>
              <el-table-column label="退货损耗" width="100" align="right">
                <template #default="{ row }">{{ fmtAmt(row.return_loss) }}</template>
              </el-table-column>
              <el-table-column label="运费" width="90" align="right">
                <template #default="{ row }">{{ fmtAmt(row.freight_amount) }}</template>
              </el-table-column>
              <el-table-column label="包装费" width="90" align="right">
                <template #default="{ row }">{{ fmtAmt(row.package_fee) }}</template>
              </el-table-column>
              <el-table-column label="运费险" width="90" align="right">
                <template #default="{ row }">{{ fmtAmt(row.freight_insurance) }}</template>
              </el-table-column>
              <el-table-column label="消费者赔付" width="100" align="right">
                <template #default="{ row }">{{ fmtAmt(row.compensation_amount) }}</template>
              </el-table-column>
              <el-table-column label="小额打款" width="100" align="right">
                <template #default="{ row }">{{ fmtAmt(row.small_payment_amount) }}</template>
              </el-table-column>
              <el-table-column label="平台其他费用" width="120" align="right">
                <template #default="{ row }">{{ fmtAmt(row.platform_other_fee) }}</template>
              </el-table-column>
              <el-table-column label="外包客服费用" width="120" align="right">
                <template #default="{ row }">{{ fmtAmt(row.customer_service_fee) }}</template>
              </el-table-column>
              <el-table-column label="推广消耗" width="100" align="right">
                <template #default="{ row }">{{ fmtAmt(row.ad_cost) }}</template>
              </el-table-column>
              <el-table-column label="人员工资" width="100" align="right">
                <template #default="{ row }">{{ fmtAmt(row.salary_fee) }}</template>
              </el-table-column>
              <el-table-column label="房租水电" width="100" align="right">
                <template #default="{ row }">{{ fmtAmt(row.rent_utility_fee) }}</template>
              </el-table-column>
              <el-table-column label="本月其他支出" width="120" align="right">
                <template #default="{ row }">{{ fmtAmt(row.other_monthly_expense) }}</template>
              </el-table-column>
              <el-table-column label="税费" width="90" align="right">
                <template #default="{ row }">{{ fmtAmt(row.tax_fee) }}</template>
              </el-table-column>
              <el-table-column label="费用合计" width="110" align="right">
                <template #default="{ row }">{{ fmtAmt(row.total_fee) }}</template>
              </el-table-column>
              <!-- 利润 -->
              <el-table-column label="订单理赔" width="100" align="right">
                <template #default="{ row }">{{ fmtAmt(row.order_claim) }}</template>
              </el-table-column>
              <el-table-column label="货值损耗" width="100" align="right">
                <template #default="{ row }">{{ fmtAmt(row.goods_loss) }}</template>
              </el-table-column>
              <el-table-column label="毛利" width="90" align="right">
                <template #default="{ row }">{{ fmtAmt(row.gross_profit) }}</template>
              </el-table-column>
              <el-table-column label="保证金充值" width="110" align="right">
                <template #default="{ row }">{{ fmtAmt(row.deposit_recharge) }}</template>
              </el-table-column>
              <el-table-column label="返佣返点" width="100" align="right">
                <template #default="{ row }">{{ fmtAmt(row.rebate_amount) }}</template>
              </el-table-column>
              <el-table-column label="净利润" width="100" align="right">
                <template #default="{ row }">
                  <span :class="parseFloat(row.net_profit) >= 0 ? 'text-profit' : 'text-loss'">
                    {{ fmtAmt(row.net_profit) }}
                  </span>
                </template>
              </el-table-column>
              <el-table-column label="净利润率" width="90" align="right">
                <template #default="{ row }">{{ fmtRate(row.net_profit_rate) }}%</template>
              </el-table-column>
              <el-table-column label="总退款率" width="90" align="right">
                <template #default="{ row }">{{ fmtRate(row.total_refund_rate) }}%</template>
              </el-table-column>
              <el-table-column label="发货前退款率" width="110" align="right">
                <template #default="{ row }">{{ fmtRate(row.before_ship_refund_rate) }}%</template>
              </el-table-column>
              <el-table-column label="发货后退款率" width="110" align="right">
                <template #default="{ row }">{{ fmtRate(row.after_ship_refund_rate) }}%</template>
              </el-table-column>
              <el-table-column label="结算后退款率" width="120" align="right">
                <template #default="{ row }">{{ fmtRate(row.after_settlement_refund_rate) }}%</template>
              </el-table-column>
              <el-table-column label="手工科目" width="100" fixed="right">
                <template #default="{ row }"><el-button link type="primary" @click="openManualEdit(row)">补录</el-button></template>
              </el-table-column>
            </el-table>
          </div>
          <el-empty v-else description="请先生成月报" />
        </el-tab-pane>

        <!-- ── Tab4: 待结算订单 ────────────────────────── -->
        <el-tab-pane label="待结算订单" name="pending_orders">
          <div class="order-filter">
            <el-input v-model="orderFilter.store_name" placeholder="店铺名称" clearable style="width:160px" @change="loadOrders('pending')" />
            <el-button @click="loadOrders('pending')">查询</el-button>
            <el-button @click="doExport('pending')" style="margin-left:auto">导出待结算</el-button>
          </div>
          <el-table :data="orderListPending" v-loading="orderLoading" border size="small" style="margin-top:8px">
            <el-table-column prop="store_name" label="店铺" width="120" show-overflow-tooltip />
            <el-table-column prop="main_order_no" label="主订单" width="150" show-overflow-tooltip />
            <el-table-column prop="sub_order_no" label="子订单" width="150" show-overflow-tooltip />
            <el-table-column prop="product_name" label="商品" width="160" show-overflow-tooltip />
            <el-table-column prop="sku_name" label="规格" width="100" show-overflow-tooltip />
            <el-table-column prop="quantity" label="数量" width="60" align="right" />
            <el-table-column label="应收金额" width="100" align="right">
              <template #default="{ row }">{{ fmtAmt(row.receivable_amount) }}</template>
            </el-table-column>
            <el-table-column label="收款金额" width="100" align="right">
              <template #default="{ row }">{{ fmtAmt(row.settlement_income) }}</template>
            </el-table-column>
            <el-table-column label="订单分类标签" width="110">
              <template #default="{ row }">{{ classificationLabel(row.final_status) }}</template>
            </el-table-column>
            <el-table-column prop="final_status_reason" label="判定原因" min-width="150" show-overflow-tooltip />
          </el-table>
          <el-pagination
            v-if="orderTotalPending > 0"
            v-model:current-page="orderPagePending"
            v-model:page-size="orderPageSize"
            :total="orderTotalPending"
            :page-sizes="[50, 100, 200]"
            layout="total, sizes, prev, pager, next"
            style="margin-top:12px"
            @current-change="loadOrders('pending')"
            @size-change="loadOrders('pending')"
          />
        </el-tab-pane>

        <!-- ── Tab5: 异常订单 ──────────────────────────── -->
        <el-tab-pane label="异常订单" name="abnormal_orders">
          <div class="order-filter">
            <el-input v-model="orderFilter.store_name" placeholder="店铺名称" clearable style="width:160px" @change="loadOrders('abnormal')" />
            <el-button @click="loadOrders('abnormal')">查询</el-button>
            <el-button type="success" :loading="exportingNormal" @click="doExportNormal" style="margin-left:auto">导出正常</el-button>
            <el-button @click="doExport('abnormal')" style="margin-left:8px">导出异常</el-button>
          </div>
          <el-table :data="orderListAbnormal" v-loading="orderLoading" border size="small" style="margin-top:8px">
            <el-table-column prop="store_name" label="店铺" width="120" show-overflow-tooltip />
            <el-table-column prop="main_order_no" label="主订单" width="150" show-overflow-tooltip />
            <el-table-column prop="sub_order_no" label="子订单" width="150" show-overflow-tooltip />
            <el-table-column prop="product_name" label="商品" width="160" show-overflow-tooltip />
            <el-table-column prop="quantity" label="数量" width="60" align="right" />
            <el-table-column label="应收金额" width="100" align="right">
              <template #default="{ row }">{{ fmtAmt(row.receivable_amount) }}</template>
            </el-table-column>
            <el-table-column label="收款金额" width="100" align="right">
              <template #default="{ row }">{{ fmtAmt(row.settlement_income) }}</template>
            </el-table-column>
            <el-table-column prop="abnormal_reason" label="异常原因" min-width="160" show-overflow-tooltip />
          </el-table>
          <el-pagination
            v-if="orderTotalAbnormal > 0"
            v-model:current-page="orderPageAbnormal"
            v-model:page-size="orderPageSize"
            :total="orderTotalAbnormal"
            :page-sizes="[50, 100, 200]"
            layout="total, sizes, prev, pager, next"
            style="margin-top:12px"
            @current-change="loadOrders('abnormal')"
            @size-change="loadOrders('abnormal')"
          />
        </el-tab-pane>

        <!-- 计算日志 -->
        <el-tab-pane label="计算日志" name="calc_logs">
          <div class="order-filter" style="flex-wrap:wrap;gap:8px">
            <el-input v-model="calcLogFilter.store_name" placeholder="店铺" clearable style="width:150px" @change="loadCalcLogs(1)" />
            <el-select v-model="calcLogFilter.level" placeholder="级别" clearable style="width:110px" @change="loadCalcLogs(1)">
              <el-option label="信息 info" value="info" />
              <el-option label="警告 warn" value="warn" />
              <el-option label="错误 error" value="error" />
              <el-option label="成功 success" value="success" />
            </el-select>
            <el-select v-model="calcLogFilter.field" placeholder="字段" clearable filterable style="width:150px" @change="loadCalcLogs(1)">
              <el-option v-for="f in CALC_FIELDS" :key="f.value" :label="f.label" :value="f.value" />
            </el-select>
            <el-select v-model="calcLogFilter.stage" placeholder="阶段" clearable style="width:150px" @change="loadCalcLogs(1)">
              <el-option v-for="s in CALC_STAGES" :key="s.value" :label="s.label" :value="s.value" />
            </el-select>
            <el-input v-model="calcLogFilter.keyword" placeholder="关键词" clearable style="width:150px" @change="loadCalcLogs(1)" />
            <el-button @click="loadCalcLogs(1)">刷新</el-button>
            <el-switch v-model="calcLogAuto" inline-prompt active-text="自动" inactive-text="手动" />
            <span style="color:#909399;font-size:12px">仅记录阶段汇总，不逐行写订单</span>
          </div>
          <el-table :data="calcLogs" v-loading="calcLogLoading" border size="small" max-height="460" style="margin-top:8px">
            <el-table-column label="时间" width="150">
              <template #default="{ row }">{{ fmtLogTime(row.created_at) }}</template>
            </el-table-column>
            <el-table-column label="级别" width="80">
              <template #default="{ row }"><el-tag :type="logLevelTag(row.level)" size="small">{{ row.level }}</el-tag></template>
            </el-table-column>
            <el-table-column prop="stage_name" label="阶段" width="120" show-overflow-tooltip />
            <el-table-column prop="field_name" label="字段" width="100" show-overflow-tooltip />
            <el-table-column prop="store_name" label="店铺" width="140" show-overflow-tooltip />
            <el-table-column prop="message" label="说明" min-width="300" show-overflow-tooltip />
            <el-table-column prop="row_count" label="总行数" width="90" align="right" />
            <el-table-column prop="success_count" label="成功" width="80" align="right" />
            <el-table-column prop="failed_count" label="失败" width="80" align="right" />
            <el-table-column label="耗时" width="90" align="right">
              <template #default="{ row }">{{ row.duration_ms != null ? row.duration_ms + 'ms' : '-' }}</template>
            </el-table-column>
            <el-table-column label="详情" width="70" fixed="right">
              <template #default="{ row }">
                <el-button v-if="row.detail_json" link type="primary" size="small" @click="showLogDetail(row)">详情</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-pagination
            v-if="calcLogTotal > 0"
            :current-page="calcLogPage"
            :page-size="calcLogPageSize"
            :total="calcLogTotal"
            layout="total, prev, pager, next"
            small
            style="margin-top:8px"
            @current-change="loadCalcLogs"
          />
        </el-tab-pane>

      </el-tabs>
    </div>

    <!-- ════ 计算日志详情 Dialog ════ -->
    <el-dialog v-model="logDetailVisible" title="计算日志详情" width="660px">
      <div style="margin-bottom:8px;color:#606266">{{ logDetailRow?.stage_name }} · {{ logDetailRow?.message }}</div>
      <pre style="max-height:480px;overflow:auto;background:#f5f7fa;padding:12px;border-radius:4px;font-size:12px;white-space:pre-wrap;word-break:break-all">{{ logDetailText }}</pre>
    </el-dialog>

    <!-- ════ 新建批次 Dialog ════ -->
    <el-dialog v-model="createBatchVisible" title="新建批次" width="480px">
      <el-form :model="createBatchForm" label-width="90px" :rules="createBatchRules" ref="createBatchFormRef">
        <el-form-item label="月份" prop="month">
          <el-date-picker v-model="createBatchForm.month" type="month" value-format="YYYY-MM" style="width:100%" />
        </el-form-item>
        <el-form-item label="报表范围" prop="scope_type">
          <el-select v-model="createBatchForm.scope_type" style="width:100%" @change="createBatchForm.scope_name = ''">
            <el-option label="全部店铺" value="all_stores" />
            <el-option label="按合伙人" value="partner" />
            <el-option label="自定义分组" value="custom_group" />
            <el-option label="单店铺" value="single_store" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="createBatchForm.scope_type !== 'all_stores'" :label="scopeNameLabel(createBatchForm.scope_type)" prop="scope_name">
          <el-input v-model="createBatchForm.scope_name" style="width:100%" />
        </el-form-item>
        <el-form-item label="批次名称" prop="batch_name">
          <el-input v-model="createBatchForm.batch_name" placeholder="留空则自动生成" style="width:100%" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="createBatchForm.remark" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createBatchVisible = false">取消</el-button>
        <el-button type="primary" :loading="createBatchLoading" @click="doCreateBatch">创建</el-button>
      </template>
    </el-dialog>

    <!-- ════ 生成月报 Dialog ════ -->
    <el-dialog v-model="generateDialogVisible" title="生成月报" width="520px" @open="onGenerateDialogOpen">
      <el-form label-width="90px">
        <el-form-item label="生成模式">
          <el-radio-group v-model="generateMode" @change="runPrecheck">
            <el-radio value="loose">宽松模式（缺文件店铺标异常，不阻断）</el-radio>
            <el-radio value="strict">严格模式（缺必传文件直接报错）</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>

      <!-- precheck 结果 -->
      <div v-if="precheckLoading" style="text-align:center;padding:12px">
        <el-icon class="is-loading"><Loading /></el-icon> 检查中...
      </div>
      <div v-else-if="precheckResult" style="margin-top:4px">
        <el-descriptions :column="2" border size="small" style="margin-bottom:10px">
          <el-descriptions-item label="预期店铺数">{{ precheckResult.expected_store_count }}</el-descriptions-item>
          <el-descriptions-item label="可生成店铺">
            <el-tag :type="precheckResult.can_generate_count > 0 ? 'success' : 'danger'" size="small">
              {{ precheckResult.can_generate_count }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="已上传">{{ precheckResult.uploaded_store_count }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="precheckResult.ok ? 'success' : 'warning'" size="small">
              {{ precheckResult.ok ? '可以生成' : '存在问题' }}
            </el-tag>
          </el-descriptions-item>
        </el-descriptions>

        <!-- 阻断错误 -->
        <el-alert v-if="precheckResult.blocking_errors.length" type="error" :closable="false" style="margin-bottom:8px">
          <template #title>阻断错误（必须修复）</template>
          <ul style="margin:4px 0;padding-left:16px">
            <li v-for="e in precheckResult.blocking_errors" :key="e" style="font-size:12px">{{ e }}</li>
          </ul>
        </el-alert>

        <!-- 警告 -->
        <el-alert v-if="precheckResult.warnings.length" type="warning" :closable="false" style="margin-bottom:8px">
          <template #title>警告（宽松模式可继续）</template>
          <ul style="margin:4px 0;padding-left:16px">
            <li v-for="w in precheckResult.warnings" :key="w" style="font-size:12px">{{ w }}</li>
          </ul>
        </el-alert>

        <!-- 店铺明细 -->
        <el-table v-if="precheckResult.stores.length" :data="precheckResult.stores" border size="small" max-height="200">
          <el-table-column prop="store_name" label="店铺" min-width="120" show-overflow-tooltip />
          <el-table-column label="缺必传" width="160">
            <template #default="{ row }">
              <el-tag v-for="t in row.required_missing" :key="t" type="danger" size="small" style="margin:2px">{{ fileTypeLabel(t) }}</el-tag>
              <span v-if="!row.required_missing.length" style="color:#67c23a;font-size:12px">✓ 齐全</span>
            </template>
          </el-table-column>
          <el-table-column label="可生成" width="80">
            <template #default="{ row }">
              <el-tag :type="row.can_generate ? 'success' : 'danger'" size="small">{{ row.can_generate ? '是' : '否' }}</el-tag>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 生成进度（异步任务） -->
      <div v-if="genTask" class="gen-progress" style="margin-top:12px;border-top:1px solid #ebeef5;padding-top:12px">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
          <span style="font-weight:600">生成进度</span>
          <el-tag :type="genStatusTag" size="small">{{ genStatusLabel }}</el-tag>
        </div>
        <el-progress
          :percentage="genTask.progress || 0"
          :status="genTask.status === 'failed' ? 'exception' : (genTask.status === 'success' ? 'success' : undefined)"
          :stroke-width="14"
        />
        <div style="margin-top:8px;color:#606266;font-size:13px">
          当前步骤：{{ stepLabel(genTask.current_step) }}
        </div>
        <div v-if="genLatestLog" style="margin-top:4px;color:#909399;font-size:12px">
          最新日志：{{ genLatestLog }}
        </div>
        <el-alert
          v-if="genTask.status === 'failed' && genTask.error_message"
          type="error" :closable="false" show-icon style="margin-top:8px"
          title="生成失败">
          <div style="white-space:pre-line;font-size:12px">{{ genTask.error_message }}</div>
        </el-alert>
      </div>

      <template #footer>
        <el-button @click="generateDialogVisible = false">{{ generating ? '关闭' : '取消' }}</el-button>
        <el-button
          type="primary"
          :loading="generating"
          :disabled="generating || (precheckResult && generateMode === 'strict' && precheckResult.blocking_errors.length > 0)"
          @click="doGenerate"
        >{{ generating ? '生成中…' : '开始生成' }}</el-button>
      </template>
    </el-dialog>

    <!-- ════ 待确认文件 Dialog ════ -->
    <el-dialog v-model="confirmDialogVisible" title="待确认文件" width="700px">
      <el-table :data="unconfirmedFiles" border size="small">
        <el-table-column prop="original_filename" label="文件名" min-width="200" show-overflow-tooltip />
        <el-table-column label="识别文件类型" width="120">
          <template #default="{ row }">{{ row.detected_file_type ? fileTypeLabel(row.detected_file_type) : '未识别' }}</template>
        </el-table-column>
        <el-table-column prop="detected_store_name" label="识别店铺" width="130" />
        <el-table-column prop="detect_message" label="提示" width="160" show-overflow-tooltip />
        <el-table-column label="操作" width="80" fixed="right">
          <template #default="{ row }"><el-button type="primary" link size="small" @click="openOneConfirm(row)">确认</el-button></template>
        </el-table-column>
      </el-table>
      <template #footer><el-button @click="confirmDialogVisible = false">关闭</el-button></template>
    </el-dialog>

    <!-- 确认单条文件 -->
    <el-dialog v-model="oneConfirmVisible" title="确认文件归属" width="400px">
      <el-form :model="oneConfirmForm" label-width="90px">
        <el-form-item label="店铺名称"><el-input v-model="oneConfirmForm.store_name" /></el-form-item>
        <el-form-item label="文件类型">
          <el-select v-model="oneConfirmForm.file_type" style="width:100%">
            <el-option v-for="ft in FILE_TYPE_OPTIONS" :key="ft.value" :label="ft.label" :value="ft.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="原文件名"><div class="text-muted" style="font-size:12px">{{ confirmingFile?.original_filename }}</div></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="oneConfirmVisible = false">取消</el-button>
        <el-button type="primary" :loading="oneConfirmLoading" @click="doOneConfirm">确认</el-button>
      </template>
    </el-dialog>

    <!-- ════ 店铺归属配置 Drawer ════ -->
    <el-drawer v-model="ownershipDrawerVisible" title="店铺归属配置" size="70%">
      <div class="ownership-toolbar">
        <el-input v-model="ownershipFilter.partner_name" placeholder="合伙人" clearable style="width:130px" @change="loadOwnerships" />
        <el-select v-model="ownershipFilter.is_active" placeholder="状态" clearable style="width:100px;margin-left:8px" @change="loadOwnerships">
          <el-option label="启用" :value="true" /><el-option label="停用" :value="false" />
        </el-select>
        <el-button type="primary" style="margin-left:auto" @click="openOwnershipCreate"><el-icon><Plus /></el-icon> 新增</el-button>
      </div>
      <el-table :data="ownerships" border size="small" v-loading="ownershipLoading" style="margin-top:8px">
        <el-table-column prop="store_name" label="店铺" width="140" show-overflow-tooltip />
        <el-table-column prop="platform" label="平台" width="90" />
        <el-table-column prop="partner_name" label="合伙人" width="100" />
        <el-table-column prop="group_name" label="分组" width="100" />
        <el-table-column prop="effective_month" label="生效月" width="85" />
        <el-table-column prop="end_month" label="结束月" width="85">
          <template #default="{ row }">{{ row.end_month || '-' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="70">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'" size="small">{{ row.is_active ? '启用' : '停用' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="120" show-overflow-tooltip />
        <el-table-column label="操作" width="110" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="openOwnershipEdit(row)">编辑</el-button>
            <el-button v-if="row.is_active" type="danger" link size="small" @click="doDeactivateOwnership(row)">停用</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-dialog v-model="ownershipFormVisible" :title="ownershipFormMode === 'create' ? '新增店铺归属' : '编辑店铺归属'" width="440px" append-to-body>
        <el-form :model="ownershipForm" label-width="90px">
          <el-form-item label="店铺名称" required><el-input v-model="ownershipForm.store_name" /></el-form-item>
          <el-form-item label="平台"><el-input v-model="ownershipForm.platform" placeholder="如：抖音、快手" /></el-form-item>
          <el-form-item label="合伙人"><el-input v-model="ownershipForm.partner_name" /></el-form-item>
          <el-form-item label="分组名称"><el-input v-model="ownershipForm.group_name" /></el-form-item>
          <el-form-item label="生效月份" required>
            <el-date-picker v-model="ownershipForm.effective_month" type="month" value-format="YYYY-MM" style="width:100%" />
          </el-form-item>
          <el-form-item label="结束月份">
            <el-date-picker v-model="ownershipForm.end_month" type="month" value-format="YYYY-MM" style="width:100%" clearable />
          </el-form-item>
          <el-form-item label="备注"><el-input v-model="ownershipForm.remark" type="textarea" :rows="2" /></el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="ownershipFormVisible = false">取消</el-button>
          <el-button type="primary" :loading="ownershipFormLoading" @click="doSaveOwnership">保存</el-button>
        </template>
      </el-dialog>
    </el-drawer>

    <el-dialog v-model="manualVisible" :title="`手工补录 - ${manualStore}`" width="520px">
      <el-form label-width="130px">
        <el-form-item label="客服费用"><el-input-number v-model="manualForm.customer_service_fee" :precision="2" :controls="false" /></el-form-item>
        <el-form-item label="管理费用"><el-input-number v-model="manualForm.management_fee" :precision="2" :controls="false" /></el-form-item>
        <el-form-item label="税务"><el-input-number v-model="manualForm.tax_fee" :precision="2" :controls="false" /></el-form-item>
        <el-form-item label="订单理赔"><el-input-number v-model="manualForm.order_claim" :precision="2" :controls="false" /></el-form-item>
        <el-form-item label="返佣返点"><el-input-number v-model="manualForm.rebate_amount" :precision="2" :controls="false" /></el-form-item>
        <el-form-item label="保证金"><el-input-number v-model="manualForm.deposit_recharge" :precision="2" :controls="false" /></el-form-item>
        <el-form-item label="其他扣减项"><el-input-number v-model="manualForm.other_deduction" :precision="2" :controls="false" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="manualVisible = false">取消</el-button>
        <el-button type="primary" :loading="manualSaving" @click="saveManualEdit">保存并重算</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Setting, Plus, Loading, UploadFilled, Refresh, Lightning, Download } from '@element-plus/icons-vue'
import type { UploadFile as ElUploadFile } from 'element-plus'
import * as api from '@/api/financeSalesMonthlyReport'
import type { Batch, StoreOwnership, ImportFile, BulkUploadResp, UploadMatrixResp, WorkbookUploadResult } from '@/api/financeSalesMonthlyReport'

// ─── 常量 ──────────────────────────────────────────────────
// 新版（规则优化版）：7 类表，停用 售后单 / 独立运费险表（运费险改由资金账单取）
const FILE_TYPE_OPTIONS = [
  { value: 'order',             label: '店铺订单',   required: true },
  { value: 'settlement',        label: '结算账单',   required: true },
  { value: 'shipping_order',    label: '发货订单',   required: true },
  { value: 'product_cost',      label: '商品成本表', required: true },
  { value: 'fund',              label: '资金账单',   required: false },
  { value: 'freight',           label: '运费',       required: false },
  { value: 'ad_cost',           label: '广告费',     required: false },
]
const ALL_FILE_TYPES = FILE_TYPE_OPTIONS

// ─── 批次列表 ─────────────────────────────────────────────
const batches = ref<Batch[]>([])
const batchLoading = ref(false)
const filterMonth = ref('')
const filterScopeType = ref('')
const currentBatch = ref<Batch | null>(null)
const activeTab = ref('upload')

async function loadBatches() {
  batchLoading.value = true
  try {
    const res = await api.listBatches({ month: filterMonth.value || undefined, scope_type: filterScopeType.value || undefined, limit: 50 })
    batches.value = (res as any).data?.items ?? (res as any).items ?? []
  } finally { batchLoading.value = false }
}

function onBatchSelect(row: Batch | null) {
  if (!row) return
  // 切换批次时停止上一个批次的进度轮询与日志自动刷新
  stopGenPolling()
  stopCalcLogAuto()
  genTask.value = null
  genLatestLog.value = ''
  calcLogs.value = []
  calcLogTotal.value = 0
  generating.value = false
  currentBatch.value = row
  activeTab.value = 'upload'
  bulkResult.value = null
  reportData.value = null
  unconfirmedCount.value = 0
  // 单店铺批次:自动填上传表单的店铺名;非单店铺:清空避免上一个批次残留
  if (row.scope_type === 'single_store' && row.scope_name) {
    singleUploadForm.value.store_name = row.scope_name
  } else {
    singleUploadForm.value.store_name = ''
  }
  // 切批次时清掉上一批次的已选文件,避免误上传
  singleUploadForm.value.file = null
  singleUploadRef.value?.clearFiles?.()
  loadUnconfirmedCount()
}

// ─── 批次创建 ─────────────────────────────────────────────
const createBatchVisible = ref(false)
const createBatchLoading = ref(false)
const createBatchFormRef = ref()
const createBatchForm = ref({ month: '', scope_type: 'all_stores', scope_name: '', batch_name: '', remark: '' })
const createBatchRules = {
  month: [{ required: true, message: '请选择月份', trigger: 'change' }],
}

function openCreateBatch() {
  createBatchForm.value = { month: filterMonth.value || '', scope_type: 'all_stores', scope_name: '', batch_name: '', remark: '' }
  createBatchVisible.value = true
}

async function doCreateBatch() {
  await createBatchFormRef.value?.validate()
  createBatchLoading.value = true
  try {
    await api.createBatch({ month: createBatchForm.value.month, scope_type: createBatchForm.value.scope_type, scope_name: createBatchForm.value.scope_name || undefined, batch_name: createBatchForm.value.batch_name || '', remark: createBatchForm.value.remark || undefined })
    ElMessage.success('批次创建成功')
    createBatchVisible.value = false
    await loadBatches()
  } catch (e: any) { ElMessage.error(e?.response?.data?.detail || '创建失败') }
  finally { createBatchLoading.value = false }
}

function doLock(row: Batch) {
  ElMessageBox.confirm(`确认锁定批次「${row.batch_name}」？`, '确认锁定', { type: 'warning' })
    .then(() => api.lockBatch(row.id)).then(() => { ElMessage.success('已锁定'); loadBatches() }).catch(() => {})
}

async function doDeleteBatch(row: Batch) {
  // locked / processing 直接拦截，不弹普通确认框
  if (row.status === 'locked') {
    ElMessage.warning('该批次已锁定，不能删除。如需删除，请先解锁。')
    return
  }
  if (row.status === 'processing') {
    ElMessage.warning('该批次正在生成中，不能删除')
    return
  }
  const completedTip = row.status === 'completed'
    ? '<div style="color:#E6A23C;margin-top:8px">⚠ 该批次已生成过月报，请确认这不是正式报表。删除后将从列表隐藏。</div>'
    : ''
  const html =
    `<div style="line-height:1.8">` +
    `批次名称：${row.batch_name}<br/>` +
    `月份：${row.month}<br/>` +
    `范围：${scopeTypeLabel(row.scope_type)}${row.scope_name ? '（' + row.scope_name + '）' : ''}<br/>` +
    `状态：${statusLabel(row.status)}` +
    `</div>${completedTip}`
  try {
    await ElMessageBox.confirm(html, '确认删除销售月报批次？', {
      type: 'warning',
      dangerouslyUseHTMLString: true,
      confirmButtonText: '确认删除',
      cancelButtonText: '取消',
      confirmButtonClass: 'el-button--danger',
    })
  } catch {
    return  // 用户取消
  }
  try {
    await api.deleteBatch(row.id)
    ElMessage.success('删除成功')
    // 若删除的是当前展开批次，关闭详情面板
    if (currentBatch.value?.id === row.id) currentBatch.value = null
    await loadBatches()
  } catch (e: any) {
    ElMessage.error(extractErrMsg(e, '删除失败'))
  }
}

// ─── 单文件上传 ───────────────────────────────────────────
const uploadMode = ref<'single' | 'bulk' | 'matrix' | 'workbook' | 'bulk_workbook'>('single')
const singleUploadForm = ref({ file_type: '', store_name: '', file: null as File | null })
const singleUploading = ref(false)
const singleUploadRef = ref<any>(null)

const isBatchLocked = computed(() => currentBatch.value?.status === 'locked')

function onSingleFileChange(f: ElUploadFile) {
  // el-upload 在 :auto-upload=false + 多次选择时会保留多个项,以最后一次为准
  singleUploadForm.value.file = f.raw ?? null
  const name = (f.name || '').toLowerCase()
  if (name.endsWith('.xls') && !name.endsWith('.xlsx')) {
    ElMessage.warning('建议另存为 .xlsx 后上传，.xls 可能无法解析')
  }
}

function onSingleFileRemove() {
  singleUploadForm.value.file = null
}

function extractErrMsg(e: any, fallback: string): string {
  const d = e?.response?.data
  if (!d) return e?.message || fallback
  if (typeof d.detail === 'string') return d.detail
  if (Array.isArray(d.detail)) {
    return d.detail.map((x: any) => x.msg || JSON.stringify(x)).join('；') || fallback
  }
  return d.message || fallback
}

async function doSingleUpload() {
  // 全显式校验,任何缺失都给明确提示,不静默 return
  if (!currentBatch.value) {
    ElMessage.warning('请先选择或创建月报批次')
    return
  }
  if (isBatchLocked.value) {
    ElMessage.warning('当前批次已锁定，不能上传文件')
    return
  }
  if (!singleUploadForm.value.file_type) {
    ElMessage.warning('请选择文件类型')
    return
  }
  // 单店铺批次:店铺名为空时自动取批次 scope_name
  if (!singleUploadForm.value.store_name
      && currentBatch.value.scope_type === 'single_store'
      && currentBatch.value.scope_name) {
    singleUploadForm.value.store_name = currentBatch.value.scope_name
  }
  if (!singleUploadForm.value.store_name) {
    ElMessage.warning('请输入店铺名称，或使用批量上传自动识别')
    return
  }
  if (!singleUploadForm.value.file) {
    ElMessage.warning('请选择要上传的文件')
    return
  }
  singleUploading.value = true
  // 第一步：只处理真正的上传
  try {
    await api.uploadFile(
      currentBatch.value.id,
      singleUploadForm.value.file_type,
      singleUploadForm.value.store_name,
      singleUploadForm.value.file,
    )
    ElMessage.success('上传成功')
    // 清掉文件,保留 file_type / store_name 方便连续上传
    singleUploadForm.value.file = null
    singleUploadRef.value?.clearFiles?.()
  } catch (e: any) {
    ElMessage.error(extractErrMsg(e, '上传失败，请检查文件类型、店铺名称和表头格式'))
    singleUploading.value = false
    return
  }
  // 第二步：上传成功后的刷新，失败不能再说上传失败
  try {
    await loadBatches()
    if (uploadMode.value === 'matrix') await loadMatrix()
    await loadUnconfirmedCount()
  } catch (e: any) {
    console.error('上传成功，但刷新页面数据失败:', e)
    ElMessage.warning('上传成功，但页面刷新失败，请手动刷新页面查看最新结果')
  } finally {
    singleUploading.value = false
  }
}

// ─── 批量上传 ─────────────────────────────────────────────
const bulkFileList = ref<{ name: string; raw: File }[]>([])
const bulkUploading = ref(false)
const bulkResult = ref<BulkUploadResp | null>(null)

function onBulkFileAdd(f: ElUploadFile) { if (f.raw) bulkFileList.value.push({ name: f.name, raw: f.raw }) }

async function doBulkUpload() {
  if (!currentBatch.value || bulkFileList.value.length === 0) return
  bulkUploading.value = true
  try {
    const res = await api.bulkUploadFiles(currentBatch.value.id, bulkFileList.value.map(f => f.raw))
    bulkResult.value = (res as any).data ?? res
    bulkFileList.value = []
    ElMessage.success('批量上传完成')
    await loadBatches(); await loadUnconfirmedCount()
  } catch (e: any) { ElMessage.error(e?.response?.data?.detail || '批量上传失败') }
  finally { bulkUploading.value = false }
}

// ─── 待确认文件 ───────────────────────────────────────────
const unconfirmedCount = ref(0)
const unconfirmedFiles = ref<ImportFile[]>([])
const confirmDialogVisible = ref(false)
const oneConfirmVisible = ref(false)
const oneConfirmLoading = ref(false)
const confirmingFile = ref<ImportFile | null>(null)
const oneConfirmForm = ref({ store_name: '', file_type: '' })

async function loadUnconfirmedCount() {
  if (!currentBatch.value) return
  try {
    const res = await api.getUnconfirmedFiles(currentBatch.value.id)
    const items: ImportFile[] = (res as any).data ?? res
    unconfirmedCount.value = items.length
    unconfirmedFiles.value = items
  } catch {}
}

function openConfirmDialog() { loadUnconfirmedCount(); confirmDialogVisible.value = true }

function openOneConfirm(row: ImportFile) {
  confirmingFile.value = row
  oneConfirmForm.value = { store_name: row.detected_store_name ?? '', file_type: row.detected_file_type ?? '' }
  oneConfirmVisible.value = true
}

async function doOneConfirm() {
  if (!currentBatch.value || !confirmingFile.value) return
  oneConfirmLoading.value = true
  try {
    await api.confirmFile(currentBatch.value.id, confirmingFile.value.id, { store_name: oneConfirmForm.value.store_name, file_type: oneConfirmForm.value.file_type })
    ElMessage.success('确认成功')
    oneConfirmVisible.value = false
    await loadUnconfirmedCount(); await loadBatches()
  } catch (e: any) { ElMessage.error(e?.response?.data?.detail || '确认失败') }
  finally { oneConfirmLoading.value = false }
}

// ─── 上传进度矩阵 ─────────────────────────────────────────
const matrixData = ref<UploadMatrixResp | null>(null)
const matrixLoading = ref(false)

async function loadMatrix() {
  if (!currentBatch.value) return
  matrixLoading.value = true
  try {
    const res = await api.getUploadMatrix(currentBatch.value.id)
    matrixData.value = (res as any).data ?? res
  } catch (e: any) { ElMessage.error(e?.response?.data?.detail || '加载矩阵失败') }
  finally { matrixLoading.value = false }
}

watch(uploadMode, v => { if (v === 'matrix') loadMatrix() })

// ─── 工作簿上传 ───────────────────────────────────────────
const wbStoreName = ref('')
const wbFile = ref<File | null>(null)
const wbFileInput = ref<HTMLInputElement>()
const wbResult = ref<WorkbookUploadResult | null>(null)
const wbUploading = ref(false)
const bulkWbFiles = ref<File[]>([])
const bulkWbFileInput = ref<HTMLInputElement>()
const bulkWbResults = ref<WorkbookUploadResult[]>([])
const bulkWbUploading = ref(false)

// 切换批次时，单店铺批次自动填店铺名
watch(currentBatch, (b) => {
  if (b?.scope_type === 'single_store' && b.scope_name) {
    wbStoreName.value = b.scope_name
  }
}, { immediate: true })

const WB_EXT_RE = /\.(xlsx|xlsm|xltx|xltm)$/i

function onWbFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  const f = input.files?.[0] ?? null
  if (f && f.name.toLowerCase().endsWith('.csv')) {
    ElMessage.warning('工作簿上传只支持 .xlsx 文件，CSV 请使用单表上传。')
    input.value = ''
    wbFile.value = null
    return
  }
  if (f && !WB_EXT_RE.test(f.name)) {
    ElMessage.warning('工作簿上传只支持 .xlsx/.xlsm/.xltx/.xltm 文件')
    input.value = ''
    wbFile.value = null
    return
  }
  wbFile.value = f
}

function onBulkWbFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  const all = input.files ? Array.from(input.files) : []
  const csvCount = all.filter(f => f.name.toLowerCase().endsWith('.csv')).length
  const valid = all.filter(f => WB_EXT_RE.test(f.name))
  if (csvCount > 0) {
    ElMessage.warning('工作簿上传只支持 .xlsx 文件，CSV 请使用单表上传。已自动忽略 CSV 文件。')
  } else if (valid.length < all.length) {
    ElMessage.warning('已忽略非 .xlsx/.xlsm/.xltx/.xltm 的文件')
  }
  bulkWbFiles.value = valid
}

async function doUploadWorkbook() {
  if (!currentBatch.value) {
    ElMessage.warning('请先选择月报批次')
    return
  }
  if (!wbStoreName.value.trim()) {
    ElMessage.warning('请输入店铺名称')
    return
  }
  if (!wbFile.value) {
    ElMessage.warning('请选择 Excel 工作簿')
    return
  }
  const fname = wbFile.value.name.toLowerCase()
  if (fname.endsWith('.csv')) {
    ElMessage.warning('工作簿上传只支持 .xlsx 文件，CSV 请使用单表上传。')
    return
  }
  if (!WB_EXT_RE.test(fname)) {
    ElMessage.warning('工作簿上传只支持 .xlsx/.xlsm/.xltx/.xltm 文件')
    return
  }
  wbUploading.value = true
  wbResult.value = null
  try {
    // interceptor 已经返回 res.data，所以 res 本身就是数据对象
    const r = await api.uploadWorkbook(
      currentBatch.value.id,
      wbStoreName.value.trim(),
      wbFile.value,
      currentBatch.value?.scope_type,
      currentBatch.value?.scope_name,
    ) as any
    wbResult.value = r
    // 显示状态提示
    if (r.message) {
      ElMessage.warning(r.message)  // 例：文件已更新，请重新生成月报
    }
    if (r.detected_count === 0 && r.need_confirm_count === 0) {
      ElMessage.warning('未识别到有效工作表，请检查 Sheet 名称是否规范')
    } else if (r.failed_count > 0 || r.need_confirm_count > 0) {
      ElMessage.warning(`工作簿上传成功，但有 ${r.failed_count} 个 Sheet 失败、${r.need_confirm_count} 个需确认，请查看解析结果`)
    } else {
      ElMessage.success(`工作簿上传成功，识别 ${r.detected_count} 个工作表`)
    }
    // 刷新批次列表和上传矩阵
    await loadBatches()
    await loadMatrix()
    // 刷新当前批次信息
    if (currentBatch.value) {
      const updatedBatches = await api.listBatches({ limit: 50 })
      const updated = (updatedBatches as any).items?.find((b: any) => b.id === currentBatch.value!.id)
      if (updated) currentBatch.value = updated
    }
  } catch (e: any) {
    const detail = e?.response?.data?.detail
      || e?.response?.data?.message
      || e?.message
      || '上传失败，请检查网络连接或文件格式'
    ElMessage({
      message: detail,
      type: 'error',
      duration: 6000,
      showClose: true,
    })
  } finally {
    wbUploading.value = false
  }
}

async function doBulkUploadWorkbooks() {
  if (!bulkWbFiles.value.length) {
    ElMessage.warning('请选择工作簿文件')
    return
  }
  bulkWbUploading.value = true
  bulkWbResults.value = []
  try {
    const res = await api.bulkUploadWorkbooks(currentBatch.value!.id, bulkWbFiles.value)
    bulkWbResults.value = ((res as any).data?.results) || []
    ElMessage.success(`批量上传完成，共 ${(res as any).data?.total_workbooks ?? bulkWbResults.value.length} 个工作簿`)
    await loadBatches()
    if (uploadMode.value === 'matrix') await loadMatrix()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '批量上传失败')
  } finally {
    bulkWbUploading.value = false
  }
}

function sheetStatusType(status: string): '' | 'success' | 'warning' | 'danger' | 'info' {
  const map: Record<string, '' | 'success' | 'warning' | 'danger' | 'info'> = {
    detected: 'success',
    need_confirm: 'warning',
    failed: 'danger',
    skipped: 'info',
  }
  return map[status] ?? ''
}

function sheetStatusLabel(status: string): string {
  const map: Record<string, string> = {
    detected: '已识别',
    need_confirm: '待确认',
    failed: '失败',
    skipped: '已跳过',
  }
  return map[status] ?? status
}

// ─── 生成月报 ─────────────────────────────────────────────
const generateDialogVisible = ref(false)
const generateMode = ref<'loose' | 'strict'>('loose')
const generating = ref(false)
const reportData = ref<any>(null)
const manualVisible = ref(false)
const manualSaving = ref(false)
const manualStore = ref('')
const manualForm = ref({ customer_service_fee: 0, management_fee: 0, tax_fee: 0, order_claim: 0, rebate_amount: 0, deposit_recharge: 0, other_deduction: 0 })

function openManualEdit(row: any) {
  manualStore.value = row.store_name
  manualForm.value = {
    customer_service_fee: Number(row.customer_service_fee || 0), management_fee: Number(row.management_fee || 0),
    tax_fee: Number(row.tax_fee || 0), order_claim: Number(row.order_claim || 0),
    rebate_amount: Number(row.rebate_amount || 0), deposit_recharge: Number(row.deposit_recharge || 0),
    other_deduction: Number(row.other_deduction || 0),
  }
  manualVisible.value = true
}

async function saveManualEdit() {
  if (!currentBatch.value || !manualStore.value) return
  manualSaving.value = true
  try {
    await api.updateReportManual(currentBatch.value.id, manualStore.value, manualForm.value)
    ElMessage.success('手工科目已保存，利润已重算')
    manualVisible.value = false
    await loadReport()
  } catch (e: any) { ElMessage.error(extractErrMsg(e, '保存失败')) }
  finally { manualSaving.value = false }
}
const precheckResult = ref<any>(null)
const precheckLoading = ref(false)

// ── 异步生成任务 ──
const genTask = ref<any>(null)
const genLatestLog = ref('')
let genTimer: ReturnType<typeof setInterval> | null = null
let genFailCount = 0

const GEN_STEP_LABELS: Record<string, string> = {
  pending: '排队中', precheck: '正在进行生成前检查', load_files: '正在读取上传文件',
  parse_orders: '正在解析店铺订单', parse_settlement: '正在解析结算账单',
  parse_after_sale: '正在解析售后单', parse_cost: '正在匹配商品成本',
  classify_orders: '正在判定订单状态', aggregate_shop: '正在汇总店铺月报',
  write_reports: '正在写入月报结果', finish: '生成完成', failed: '生成失败',
}
function stepLabel(step?: string) { return (step && GEN_STEP_LABELS[step]) || '处理中' }

const genStatusLabel = computed(() => {
  const m: Record<string, string> = { pending: '排队中', running: '生成中', success: '已完成', failed: '失败', cancelled: '已取消' }
  return m[genTask.value?.status] ?? genTask.value?.status ?? ''
})
const genStatusTag = computed(() => {
  const m: Record<string, any> = { pending: 'info', running: 'warning', success: 'success', failed: 'danger', cancelled: 'info' }
  return m[genTask.value?.status] ?? 'info'
})

function stopGenPolling() {
  if (genTimer) { clearInterval(genTimer); genTimer = null }
}

function onGenerateDialogOpen() {
  runPrecheck()
  // 恢复尚未结束的任务进度（页面刷新/重开弹窗后）
  if (currentBatch.value) {
    api.getLatestGenerateTask(currentBatch.value.id).then((res: any) => {
      const t = (res as any)?.data ?? res
      if (t && (t.status === 'pending' || t.status === 'running')) {
        genTask.value = t
        generating.value = true
        startGenPolling(t.id)
      }
    }).catch(() => {})
  }
}

function openGenerateDialog() {
  genTask.value = null
  genLatestLog.value = ''
  generateDialogVisible.value = true
}

async function runPrecheck() {
  if (!currentBatch.value) return
  precheckLoading.value = true
  precheckResult.value = null
  try {
    const res = await api.precheckBatch(currentBatch.value.id, generateMode.value)
    precheckResult.value = (res as any).data ?? res
  } catch { /* ignore */ }
  finally { precheckLoading.value = false }
}

async function refreshGenLatestLog(taskId: number) {
  if (!currentBatch.value) return
  try {
    const res: any = await api.getCalcLogs(currentBatch.value.id, { task_id: taskId, page_size: 500 })
    const items = (res.data?.items ?? res.items ?? [])
    if (items.length) genLatestLog.value = items[items.length - 1].message
    // 计算日志 Tab 打开且自动刷新时，同步刷新表格
    if (activeTab.value === 'calc_logs' && calcLogAuto.value) loadCalcLogs(calcLogPage.value)
  } catch { /* 日志查询失败不影响主流程 */ }
}

function startGenPolling(taskId: number) {
  stopGenPolling()
  genFailCount = 0
  genTimer = setInterval(async () => {
    try {
      const res = await api.getGenerateTask(taskId)
      genFailCount = 0  // 查询成功，重置失败计数
      const t: any = (res as any).data ?? res
      genTask.value = t
      await refreshGenLatestLog(taskId)
      if (t.status === 'success') {
        stopGenPolling()
        generating.value = false
        ElMessage.success(t.message || '生成成功')
        await onGenerateSuccess()
      } else if (t.status === 'failed' || t.status === 'cancelled') {
        stopGenPolling()
        generating.value = false
        showGenerateError(t.error_message || t.message || '生成失败')
      }
    } catch (e: any) {
      // 任务不存在（已清理）→ 停止
      if (e?.response?.status === 404) {
        stopGenPolling()
        generating.value = false
        ElMessage.warning('生成任务不存在，可能已被清理。')
        return
      }
      // 临时失败：3 次以内提示重试，不判定任务失败、不停止轮询
      genFailCount++
      if (genFailCount < 3) {
        ElMessage.warning('任务状态查询暂时失败，系统正在重试。')
      } else if (genFailCount === 3) {
        ElMessage.warning('任务状态查询失败，请刷新页面查看。')
      }
    }
  }, 3000)
}

async function onGenerateSuccess() {
  // 刷新批次列表 + 简版看板/完整月报 + 待结算订单 + 异常订单
  await loadBatches()
  if (currentBatch.value) {
    const updated = await api.listBatches({ limit: 50 }) as any
    const u = (updated.items ?? updated.data?.items ?? []).find((b: any) => b.id === currentBatch.value!.id)
    if (u) currentBatch.value = u
  }
  await loadReport()
  await loadOrders('pending')
  await loadOrders('abnormal')
  await loadCalcLogs(1)
  activeTab.value = 'simple'
  // 稍后关闭弹窗，让用户看到 100%
  setTimeout(() => { if (genTask.value?.status === 'success') generateDialogVisible.value = false }, 800)
}

function showGenerateError(detail: string) {
  const html = String(detail)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/\n/g, '<br/>')
  ElMessageBox.alert(html, '生成月报失败', {
    type: 'error',
    dangerouslyUseHTMLString: true,
    confirmButtonText: '我知道了',
  }).catch(() => {})
}

async function doGenerate() {
  if (!currentBatch.value || generating.value) return
  generating.value = true
  genLatestLog.value = ''
  genTask.value = { status: 'pending', progress: 0, current_step: 'pending', message: '任务已创建，等待执行' }
  try {
    const res = await api.generateReport(currentBatch.value.id, generateMode.value)
    const r: any = (res as any).data ?? res
    if (!r.ok) {
      // 已有任务在跑：不重复启动，直接跟踪已有任务
      ElMessage.warning(r.message || '该批次已有生成任务正在执行')
    }
    if (r.task_id) {
      startGenPolling(r.task_id)
    } else {
      generating.value = false
    }
  } catch (e: any) {
    generating.value = false
    genTask.value = null
    showGenerateError(extractErrMsg(e, '启动生成任务失败'))
  }
}

async function loadReport() {
  if (!currentBatch.value) return
  try {
    const res = await api.getReports(currentBatch.value.id)
    reportData.value = (res as any).data ?? res
  } catch {}
}

// ── 计算日志 ──
const CALC_STAGES = [
  { value: 'start', label: '开始生成' },
  { value: 'load_files', label: '读取上传文件' },
  { value: 'parse_orders', label: '解析店铺订单' },
  { value: 'parse_settlement', label: '解析结算账单' },
  { value: 'parse_after_sale', label: '解析售后单' },
  { value: 'parse_cost', label: '匹配商品成本' },
  { value: 'classify_orders', label: '判定订单状态' },
  { value: 'aggregate_shop', label: '汇总店铺月报' },
  { value: 'validate_report_values', label: '写入前金额校验' },
  { value: 'write_reports', label: '写入月报结果' },
  { value: 'validate_report_consistency', label: '结果一致性校验' },
  { value: 'finish', label: '生成结束' },
]
const CALC_FIELDS = [
  { value: 'shipped_order_count', label: '发货订单数' },
  { value: 'shipped_amount', label: '发货金额' },
  { value: 'refund_order_count', label: '退款订单数' },
  { value: 'after_ship_refund_amount', label: '发货后退款金额' },
  { value: 'actual_sales_amount', label: '实际销售额' },
  { value: 'actual_sales_order_count', label: '实销单量' },
  { value: 'avg_order_amount', label: '客单价' },
  { value: 'actual_product_cost', label: '实际销售成本' },
  { value: 'platform_service_fee', label: '平台服务费' },
  { value: 'talent_commission', label: '达人佣金' },
  { value: 'return_loss', label: '退货损耗' },
  { value: 'freight_amount', label: '运费' },
  { value: 'package_fee', label: '包装费' },
  { value: 'freight_insurance', label: '运费险' },
  { value: 'platform_other_fee', label: '平台其他费用' },
  { value: 'compensation_amount', label: '消费者赔付' },
  { value: 'small_payment_amount', label: '小额打款' },
  { value: 'ad_cost', label: '推广消耗' },
  { value: 'goods_loss', label: '货值损耗' },
  { value: 'total_fee', label: '费用合计' },
  { value: 'gross_profit', label: '毛利' },
  { value: 'net_profit', label: '净利润' },
  { value: 'net_profit_rate', label: '净利润率' },
]
const calcLogFilter = ref<{ store_name: string; level: string; stage: string; keyword: string; field: string }>(
  { store_name: '', level: '', stage: '', keyword: '', field: '' })
const calcLogs = ref<any[]>([])
const calcLogTotal = ref(0)
const calcLogPage = ref(1)
const calcLogPageSize = ref(50)
const calcLogLoading = ref(false)
const calcLogAuto = ref(true)
let calcLogTimer: ReturnType<typeof setInterval> | null = null
const logDetailVisible = ref(false)
const logDetailRow = ref<any>(null)
const logDetailText = ref('')

function logLevelTag(level: string) {
  return ({ info: 'info', warn: 'warning', error: 'danger', success: 'success' } as any)[level] ?? 'info'
}
function fmtLogTime(t?: string) {
  if (!t) return '-'
  const d = new Date(t)
  if (isNaN(d.getTime())) return t
  const p = (n: number) => String(n).padStart(2, '0')
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}
function showLogDetail(row: any) {
  logDetailRow.value = row
  try { logDetailText.value = JSON.stringify(row.detail_json, null, 2) }
  catch { logDetailText.value = String(row.detail_json) }
  logDetailVisible.value = true
}

async function loadCalcLogs(page?: number) {
  if (!currentBatch.value) return
  if (page) calcLogPage.value = page
  calcLogLoading.value = true
  try {
    const params: any = { page: calcLogPage.value, page_size: calcLogPageSize.value }
    if (calcLogFilter.value.store_name) params.store_name = calcLogFilter.value.store_name
    if (calcLogFilter.value.level) params.level = calcLogFilter.value.level
    if (calcLogFilter.value.stage) params.stage = calcLogFilter.value.stage
    if (calcLogFilter.value.field) params.field = calcLogFilter.value.field
    if (calcLogFilter.value.keyword) params.keyword = calcLogFilter.value.keyword
    const res: any = await api.getCalcLogs(currentBatch.value.id, params)
    const data = res.data ?? res
    calcLogs.value = data.items ?? []
    calcLogTotal.value = data.total ?? 0
  } catch { /* ignore */ }
  finally { calcLogLoading.value = false }
}

function stopCalcLogAuto() {
  if (calcLogTimer) { clearInterval(calcLogTimer); calcLogTimer = null }
}
function startCalcLogAuto() {
  stopCalcLogAuto()
  // 任务生成中时每 3 秒刷新；任务结束自动停
  calcLogTimer = setInterval(() => {
    const st = genTask.value?.status
    if (activeTab.value === 'calc_logs' && calcLogAuto.value && (st === 'running' || st === 'pending')) {
      loadCalcLogs(calcLogPage.value)
    } else if (st && st !== 'running' && st !== 'pending') {
      stopCalcLogAuto()
    }
  }, 3000)
}

watch(calcLogAuto, (v) => { if (v && activeTab.value === 'calc_logs') startCalcLogAuto(); else stopCalcLogAuto() })

watch(activeTab, v => {
  if ((v === 'simple' || v === 'full') && !reportData.value) loadReport()
  if (v === 'pending_orders' && orderListPending.value.length === 0) loadOrders('pending')
  if (v === 'abnormal_orders' && orderListAbnormal.value.length === 0) loadOrders('abnormal')
  if (v === 'calc_logs') {
    loadCalcLogs(1)
    if (calcLogAuto.value) startCalcLogAuto()
  } else {
    stopCalcLogAuto()
  }
})

// ─── 订单明细 ─────────────────────────────────────────────
const orderFilter = ref({ store_name: '' })
const orderPageSize = ref(50)
const orderLoading = ref(false)
const orderListPending = ref<any[]>([])
const orderListAbnormal = ref<any[]>([])
const orderTotalPending = ref(0)
const orderTotalAbnormal = ref(0)
const orderPagePending = ref(1)
const orderPageAbnormal = ref(1)

async function loadOrders(type: 'pending' | 'abnormal') {
  if (!currentBatch.value) return
  orderLoading.value = true
  try {
    const page = type === 'pending' ? orderPagePending.value : orderPageAbnormal.value
    const finalStatus = type === 'pending' ? 'pending_settlement' : 'abnormal'
    const res = await api.getOrderDetails(currentBatch.value.id, {
      store_name: orderFilter.value.store_name || undefined,
      final_status: finalStatus, page, page_size: orderPageSize.value,
    })
    const d: any = (res as any).data ?? res
    if (type === 'pending') { orderListPending.value = d.items ?? []; orderTotalPending.value = d.total ?? 0 }
    else { orderListAbnormal.value = d.items ?? []; orderTotalAbnormal.value = d.total ?? 0 }
  } finally { orderLoading.value = false }
}

// ─── 导出 ─────────────────────────────────────────────────
async function doExportReport() {
  if (!currentBatch.value) return
  try {
    const res = await api.exportReport(currentBatch.value.id)
    api.downloadBlob(res.data ?? res, `${currentBatch.value.batch_name}-月报.xlsx`)
  } catch { ElMessage.error('导出失败') }
}

async function doExport(type: 'pending' | 'abnormal') {
  if (!currentBatch.value) return
  try {
    const res = type === 'pending' ? await api.exportPending(currentBatch.value.id) : await api.exportAbnormal(currentBatch.value.id)
    const label = type === 'pending' ? '待结算' : '异常'
    api.downloadBlob(res.data ?? res, `${currentBatch.value.batch_name}-${label}.xlsx`)
  } catch { ElMessage.error('导出失败') }
}

const exportingNormal = ref(false)
async function doExportNormal() {
  if (!currentBatch.value || exportingNormal.value) return
  exportingNormal.value = true
  try {
    const res = await api.exportNormal(currentBatch.value.id)
    api.downloadBlob(res.data ?? res, `销售月报-正常订单明细-${currentBatch.value.batch_name}.xlsx`)
    ElMessage.success('正常订单明细已导出')
  } catch (e: any) {
    // 后端 blob 错误需解析出中文 message
    let msg = '导出失败'
    const d = e?.response?.data
    if (d instanceof Blob) {
      try { msg = JSON.parse(await d.text())?.detail || msg } catch { /* ignore */ }
    } else {
      msg = d?.detail || e?.message || msg
    }
    ElMessage.error(msg)
  } finally {
    exportingNormal.value = false
  }
}

// ─── 工具函数 ─────────────────────────────────────────────
function statusLabel(s: string) {
  return { draft: '草稿', processing: '处理中', completed: '已完成', failed: '失败', locked: '已锁定' }[s] ?? s
}
function statusTagType(s: string) {
  return ({ draft: 'info', processing: 'warning', completed: 'success', failed: 'danger', locked: '' } as any)[s] ?? 'info'
}
function scopeTypeLabel(s: string) {
  return { all_stores: '全部店铺', partner: '合伙人', custom_group: '自定义分组', single_store: '单店铺' }[s] ?? s
}
function scopeNameLabel(scopeType: string) {
  return { partner: '合伙人名', custom_group: '分组名', single_store: '店铺名' }[scopeType] ?? '范围名称'
}
function fileTypeLabel(ft: string) { return FILE_TYPE_OPTIONS.find(o => o.value === ft)?.label ?? ft }
function detectStatusTag(s: string) { return { detected: 'success', need_confirm: 'warning', failed: 'danger' }[s] ?? 'info' }
function detectStatusLabel(s: string) { return { detected: '已识别', need_confirm: '待确认', failed: '失败' }[s] ?? s }
function matrixCellClass(cell: any) {
  if (!cell) return 'mc-missing'
  return { uploaded: 'mc-ok', missing: 'mc-missing', need_confirm: 'mc-warn', error: 'mc-err' }[cell.status as string] ?? ''
}
function matrixCellText(cell: any) {
  if (!cell || cell.status === 'missing') return '—'
  return { uploaded: '✓', need_confirm: '?', error: '✗' }[cell.status as string] ?? cell.status
}
function storeMatrixStatusTag(s: string) {
  return ({ complete: 'success', missing_required: 'danger', missing_optional: 'warning', has_error: 'danger' } as any)[s] ?? 'info'
}
function storeMatrixStatusLabel(s: string) {
  return { complete: '完整', missing_required: '缺必传', missing_optional: '缺可选', has_error: '有错误' }[s] ?? s
}
function fmtTime(_: any, __: any, val: string) { return val ? val.slice(0, 16).replace('T', ' ') : '-' }
function fmtAmount(v: string | number) {
  return parseFloat(String(v ?? 0)).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function fmtAmt(v: string | number | null | undefined) {
  const n = parseFloat(String(v ?? 0))
  return isNaN(n) ? '0.00' : n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function fmtRate(v: string | number) { return (parseFloat(String(v ?? 0)) * 100).toFixed(2) }
function classificationLabel(v?: string) {
  return ({ pre_settlement_refund: '结算前退款', paid: '已收款', refunded: '已退款', pending_settlement: '待结算' } as any)[v || ''] || '-'
}

// 简版表格合计
function simpleTableSummary({ columns, data }: any) {
  const sumCols = ['shipped_order_count', 'actual_sales_amount', 'actual_product_cost', 'net_profit']
  return columns.map((col: any) => {
    if (col.property === 'store_name') return '合计'
    if (sumCols.includes(col.property)) {
      const sum = data.reduce((acc: number, row: any) => acc + parseFloat(row[col.property] ?? 0), 0)
      return col.property === 'shipped_order_count' ? sum : `¥${fmtAmount(sum)}`
    }
    return ''
  })
}

// 完整月报合计（金额字段合计，百分比字段为空）
const FULL_SUM_FIELDS = [
  'shipped_order_count', 'shipped_amount', 'refund_order_count', 'after_ship_refund_amount',
  'before_ship_refund_amount', 'after_settlement_refund_amount',
  'actual_sales_amount', 'actual_sales_order_count', 'actual_sales_order_completed', 'paid_sales_amount',
  'actual_product_cost', 'platform_service_fee', 'talent_commission', 'return_loss',
  'freight_amount', 'package_fee', 'freight_insurance', 'compensation_amount',
  'small_payment_amount', 'customer_service_fee', 'ad_cost', 'salary_fee',
  'rent_utility_fee', 'other_monthly_expense', 'tax_fee', 'total_fee',
  'order_claim', 'goods_loss', 'gross_profit', 'deposit_recharge',
  'rebate_amount', 'net_profit',
]
const INT_FIELDS = new Set(['shipped_order_count', 'refund_order_count', 'actual_sales_order_count', 'actual_sales_order_completed'])

function fullTableSummary({ columns, data }: any) {
  return columns.map((col: any, idx: number) => {
    if (idx === 0) return '合计'
    if (col.property === 'store_name' || col.property === 'store_code') return ''
    if (col.property?.endsWith('_rate') || col.property === 'avg_order_amount') return ''
    if (FULL_SUM_FIELDS.includes(col.property)) {
      const sum = data.reduce((acc: number, row: any) => acc + parseFloat(row[col.property] ?? 0), 0)
      return INT_FIELDS.has(col.property) ? sum : fmtAmt(sum)
    }
    return ''
  })
}

// ─── 店铺归属配置 ─────────────────────────────────────────
const ownershipDrawerVisible = ref(false)
const ownershipLoading = ref(false)
const ownerships = ref<StoreOwnership[]>([])
const ownershipFilter = ref({ partner_name: '', is_active: null as boolean | null })
const ownershipFormVisible = ref(false)
const ownershipFormMode = ref<'create' | 'edit'>('create')
const ownershipFormLoading = ref(false)
const editingOwnershipId = ref<number | null>(null)
const ownershipForm = ref({ store_name: '', platform: '', partner_name: '', group_name: '', effective_month: '', end_month: '', remark: '' })

async function loadOwnerships() {
  ownershipLoading.value = true
  try {
    const res = await api.listStoreOwnerships({ partner_name: ownershipFilter.value.partner_name || undefined, is_active: ownershipFilter.value.is_active ?? undefined, limit: 500 })
    ownerships.value = (res as any).data?.items ?? (res as any).items ?? []
  } finally { ownershipLoading.value = false }
}

watch(ownershipDrawerVisible, v => { if (v) loadOwnerships() })

function openOwnershipCreate() {
  ownershipFormMode.value = 'create'; editingOwnershipId.value = null
  ownershipForm.value = { store_name: '', platform: '', partner_name: '', group_name: '', effective_month: '', end_month: '', remark: '' }
  ownershipFormVisible.value = true
}

function openOwnershipEdit(row: StoreOwnership) {
  ownershipFormMode.value = 'edit'; editingOwnershipId.value = row.id
  ownershipForm.value = { store_name: row.store_name, platform: row.platform ?? '', partner_name: row.partner_name ?? '', group_name: row.group_name ?? '', effective_month: row.effective_month, end_month: row.end_month ?? '', remark: row.remark ?? '' }
  ownershipFormVisible.value = true
}

async function doSaveOwnership() {
  const f = ownershipForm.value
  if (!f.store_name || !f.effective_month) { ElMessage.warning('请填写店铺名称和生效月份'); return }
  ownershipFormLoading.value = true
  try {
    const payload = { store_name: f.store_name, platform: f.platform || undefined, partner_name: f.partner_name || undefined, group_name: f.group_name || undefined, effective_month: f.effective_month, end_month: f.end_month || undefined, remark: f.remark || undefined }
    if (ownershipFormMode.value === 'create') await api.createStoreOwnership(payload)
    else await api.updateStoreOwnership(editingOwnershipId.value!, payload)
    ElMessage.success('保存成功'); ownershipFormVisible.value = false; await loadOwnerships()
  } catch (e: any) { ElMessage.error(e?.response?.data?.detail || '保存失败') }
  finally { ownershipFormLoading.value = false }
}

async function doDeactivateOwnership(row: StoreOwnership) {
  await ElMessageBox.confirm(`确认停用「${row.store_name}」的归属配置？`, '确认停用', { type: 'warning' })
  try { await api.deactivateStoreOwnership(row.id); ElMessage.success('已停用'); await loadOwnerships() }
  catch (e: any) { ElMessage.error(e?.response?.data?.detail || '操作失败') }
}

onMounted(loadBatches)
onBeforeUnmount(() => { stopGenPolling(); stopCalcLogAuto() })
</script>

<style scoped>
.smr-page { padding: 16px; }
.smr-toolbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; gap: 8px; flex-wrap: wrap; }
.toolbar-left { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.scope-name { font-size: 12px; color: #909399; margin-left: 4px; }
.text-muted { color: #909399; font-size: 12px; }

.batch-detail { border: 1px solid #e4e7ed; border-radius: 6px; padding: 16px; margin-top: 8px; }
.detail-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.detail-title { font-size: 15px; font-weight: 600; }

.upload-mode-bar { display: flex; align-items: center; margin-bottom: 16px; }
.single-upload { max-width: 600px; }
.upload-lock-tip { margin-left: 8px; color: #f56c6c; font-size: 12px; }
.bulk-upload { max-width: 800px; }
.bulk-file-count { font-size: 13px; color: #606266; }
.bulk-result { margin-top: 16px; }
.bulk-result-stats { display: flex; align-items: center; gap: 4px; }

.matrix-header { display: flex; align-items: center; margin-bottom: 8px; }
.mc-ok     { color: #67c23a; font-weight: 600; }
.mc-missing { color: #c0c4cc; }
.mc-warn   { color: #e6a23c; font-weight: 600; }
.mc-err    { color: #f56c6c; font-weight: 600; }

.report-toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; }
.kpi-cards { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 16px; }
.kpi-card { flex: 1; min-width: 110px; border: 1px solid #e4e7ed; border-radius: 6px; padding: 12px 16px; text-align: center; }
.kpi-label { font-size: 12px; color: #909399; margin-bottom: 6px; }
.kpi-value { font-size: 20px; font-weight: 700; }
.kpi-primary { color: #409eff; }
.kpi-profit  { color: #67c23a; }
.kpi-loss    { color: #f56c6c; }
.kpi-warn    { color: #e6a23c; }
.kpi-danger  { color: #f56c6c; }
.text-profit { color: #67c23a; }
.text-loss   { color: #f56c6c; }

/* 完整月报横向滚动 */
.full-report-wrap { overflow-x: auto; }
.full-report-wrap :deep(.el-table) { width: max-content; min-width: 100%; }

.order-filter { display: flex; gap: 8px; margin-bottom: 8px; align-items: center; }
.ownership-toolbar { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin-bottom: 8px; }
:deep(.el-table .cell) { padding: 4px 8px; }
</style>
