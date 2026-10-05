<template>
  <section class="observability-page">
    <div class="observability-header">
      <div>
        <h1>可观测仪表盘</h1>
        <p>运行时指标、事件和各层观测数据</p>
      </div>
      <div class="toolbar">
        <a-checkbox v-model:checked="autoRefresh">自动刷新</a-checkbox>
        <a-button :loading="loading" @click="loadDashboard">刷新</a-button>
      </div>
    </div>

    <a-alert
      v-if="errorMessage"
      class="status-alert"
      type="error"
      show-icon
      :message="errorMessage"
    />

    <div class="summary-grid">
      <div v-for="item in summaryCards" :key="item.label" class="metric-card">
        <span>{{ item.label }}</span>
        <strong>{{ item.value }}</strong>
      </div>
    </div>

    <div class="panel-grid">
      <section class="panel">
        <div class="panel-title">
          <h2>HTTP 层</h2>
          <span>{{ httpSummary.total_requests || 0 }} 次请求</span>
        </div>
        <div class="metric-list">
          <div><span>平均耗时</span><strong>{{ formatMs(httpSummary.overall_avg_duration) }}</strong></div>
          <div><span>失败请求</span><strong>{{ httpSummary.failed_requests || 0 }}</strong></div>
          <div><span>业务请求</span><strong>{{ businessHttpRequests }}</strong></div>
          <div><span>慢请求</span><strong>{{ slowHttpRequests }}</strong></div>
        </div>
      </section>

      <section class="panel">
        <div class="panel-title">
          <h2>MCP / 外部服务</h2>
          <span>{{ externalHealth.overall_status || "unknown" }}</span>
        </div>
        <a-table
          size="small"
          :pagination="false"
          :columns="serviceColumns"
          :data-source="serviceRows"
          row-key="service_name"
        />
      </section>

      <section class="panel">
        <div class="panel-title">
          <h2>Agent 层</h2>
          <span>{{ agentStats.total_agents || 0 }} 个智能体</span>
        </div>
        <div class="metric-list">
          <div><span>Agent 请求</span><strong>{{ counters.agent_requests_total || 0 }}</strong></div>
          <div><span>Agent 工具调用</span><strong>{{ counters.tool_calls_total || 0 }}</strong></div>
          <div><span>Agent Token</span><strong>{{ counters.agent_tokens_total || 0 }}</strong></div>
        </div>
      </section>

      <section class="panel">
        <div class="panel-title">
          <h2>LLM 层</h2>
          <span>{{ counters.llm_calls_total || 0 }} 次调用</span>
        </div>
        <div class="metric-list">
          <div><span>输入 Token</span><strong>{{ counters.input_tokens_total || 0 }}</strong></div>
          <div><span>输出 Token</span><strong>{{ counters.output_tokens_total || 0 }}</strong></div>
          <div><span>总 Token</span><strong>{{ counters.tokens_total || 0 }}</strong></div>
        </div>
      </section>

      <section class="panel">
        <div class="panel-title">
          <h2>端到端规划</h2>
          <span>{{ counters.planning_requests_total || 0 }} 次请求</span>
        </div>
        <div class="metric-list">
          <div><span>平均总耗时</span><strong>{{ formatMs(planningDuration.avg) }}</strong></div>
          <div><span>最大总耗时</span><strong>{{ formatMs(planningDuration.max) }}</strong></div>
          <div><span>规划失败</span><strong>{{ counters.planning_errors_total || 0 }}</strong></div>
        </div>
      </section>

      <section class="panel">
        <div class="panel-title">
          <h2>上下文压缩</h2>
          <span>{{ compressionStats.total_compressions || 0 }} 次</span>
        </div>
        <div class="metric-list">
          <div><span>平均压缩比</span><strong>{{ formatRatio(compressionStats.avg_compression_ratio) }}</strong></div>
          <div><span>平均原始大小</span><strong>{{ formatNumber(compressionStats.avg_original_size) }}</strong></div>
          <div><span>平均减少大小</span><strong>{{ formatNumber(compressionStats.avg_size_reduction) }}</strong></div>
        </div>
      </section>
    </div>

    <section class="panel full">
      <div class="panel-title">
        <h2>错误来源</h2>
        <span>{{ totalErrors }} 个错误</span>
      </div>
      <a-table
        size="small"
        :pagination="false"
        :columns="errorColumns"
        :data-source="errorRows"
        row-key="source"
      />
    </section>

    <section class="panel full">
      <div class="panel-title">
        <h2>Agent 明细</h2>
        <span>{{ agentRows.length }} 个智能体</span>
      </div>
      <a-table
        size="small"
        :pagination="{ pageSize: 6 }"
        :columns="agentColumns"
        :data-source="agentRows"
        row-key="agent_name"
      />
    </section>

    <section class="panel full">
      <div class="panel-title">
        <h2>最近事件</h2>
        <span>{{ recentEvents.length }} 条</span>
      </div>
      <a-table
        size="small"
        :pagination="{ pageSize: 8 }"
        :columns="eventColumns"
        :data-source="recentEvents"
        row-key="key"
      />
    </section>

    <section class="panel full">
      <div class="panel-title">
        <h2>指标摘要</h2>
        <span>{{ lastUpdatedText }}</span>
      </div>
      <div class="raw-grid">
        <pre>{{ JSON.stringify(counters, null, 2) }}</pre>
        <pre>{{ JSON.stringify(histograms, null, 2) }}</pre>
      </div>
    </section>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import axios from "axios";

type AnyRecord = Record<string, any>;

const loading = ref(false);
const errorMessage = ref("");
const autoRefresh = ref(true);
const dashboard = ref<AnyRecord>({});
const events = ref<AnyRecord[]>([]);
const lastUpdated = ref<Date | null>(null);
let timer: number | undefined;

const counters = computed(() => dashboard.value?.summary?.counters || {});
const histograms = computed(() => dashboard.value?.summary?.histograms || {});
const httpSummary = computed(() => dashboard.value?.http?.summary || {});
const externalServices = computed(() => dashboard.value?.external_services || {});
const externalHealth = computed(() => externalServices.value?.overall_health || {});
const agentStats = computed(() => dashboard.value?.agent || {});
const sessionStats = computed(() => dashboard.value?.session || {});
const compressionStats = computed(() => sessionStats.value?.compression_stats || {});
const planningDuration = computed(() => histograms.value?.planning_total_duration || {});

const summaryCards = computed(() => [
  { label: "HTTP 请求", value: httpSummary.value.total_requests || 0 },
  { label: "端到端平均耗时", value: formatMs(planningDuration.value.avg) },
  { label: "Agent 请求", value: counters.value.agent_requests_total || 0 },
  { label: "LLM 调用", value: counters.value.llm_calls_total || 0 },
  { label: "Agent 工具调用", value: counters.value.tool_calls_total || 0 },
  { label: "上下文压缩", value: compressionStats.value.total_compressions || 0 },
  { label: "错误数", value: totalErrors.value },
]);

const totalErrors = computed(() => {
  return errorRows.value.reduce((total, row) => total + Number(row.count || 0), 0);
});

const serviceRows = computed(() => {
  const stats = externalServices.value?.services_stats || {};
  return Object.values(stats);
});

const businessHttpRequests = computed(() => {
  const endpointStats = httpSummary.value?.endpoint_statistics || {};
  return Object.entries(endpointStats).reduce((total, [endpoint, stats]: [string, any]) => {
    if (endpoint.startsWith("/api/observability") || endpoint.startsWith("/api/performance")) {
      return total;
    }
    return total + Number(stats?.count || 0);
  }, 0);
});

const slowHttpRequests = computed(() => {
  const recentRequests = dashboard.value?.http?.recent_requests || [];
  return recentRequests.filter((request: AnyRecord) => Number(request.duration || 0) >= 1).length;
});

const agentRows = computed(() => {
  const agents = agentStats.value?.agents || {};
  return Object.values(agents).map((agent: any) => {
    const summary = agent.summary || {};
    const toolCalls = agent.tool_calls || [];
    return {
      agent_name: agent.agent_name,
      success: summary.success === false ? "失败" : agent.has_execution ? "成功" : "暂无执行",
      iterations: summary.iterations || 0,
      tool_count: summary.tool_calls || 0,
      llm_count: summary.llm_calls || 0,
      duration: summary.duration || 0,
      tools: toolCalls.length
        ? toolCalls.map((tool: AnyRecord) => `${tool.tool_name}:${tool.success ? "成功" : "失败"}`).join("，")
        : "-",
      error_message: summary.error_message || "-",
    };
  });
});

const errorRows = computed(() => [
  { source: "HTTP 层", count: counters.value.http_errors_total || 0 },
  { source: "规划链路", count: counters.value.planning_errors_total || 0 },
  { source: "Agent 层", count: counters.value.agent_errors_total || 0 },
  { source: "LLM 层", count: counters.value.llm_errors_total || 0 },
  { source: "输入校验", count: counters.value.input_validation_failed_total || 0 },
  { source: "输出校验", count: counters.value.output_validation_failed_total || 0 },
  { source: "结构化解析", count: counters.value.structured_parse_errors_total || 0 },
]);

const recentEvents = computed(() => {
  return events.value.map((event, index) => ({
    key: `${event.timestamp || index}-${index}`,
    time: formatTime(event.timestamp),
    type: event.event_type,
    trace: event.trace_id || "-",
    task: event.data?.task_id || "-",
    data: JSON.stringify(event.data || {}),
  }));
});

const lastUpdatedText = computed(() => {
  return lastUpdated.value ? `最后刷新：${lastUpdated.value.toLocaleTimeString()}` : "尚未刷新";
});

const serviceColumns = [
  { title: "服务", dataIndex: "service_name" },
  { title: "状态", dataIndex: "health_status" },
  { title: "总次数", dataIndex: "total_calls" },
  { title: "成功率", dataIndex: "success_rate", customRender: ({ text }: AnyRecord) => formatPercent(text) },
  { title: "平均耗时", dataIndex: "avg_duration", customRender: ({ text }: AnyRecord) => formatMs(text) },
];

const errorColumns = [
  { title: "来源", dataIndex: "source" },
  { title: "错误数", dataIndex: "count" },
];

const agentColumns = [
  { title: "智能体", dataIndex: "agent_name", width: 180 },
  { title: "结果", dataIndex: "success", width: 90 },
  { title: "循环次数", dataIndex: "iterations", width: 100 },
  { title: "工具次数", dataIndex: "tool_count", width: 100 },
  { title: "模型调用", dataIndex: "llm_count", width: 100 },
  { title: "耗时", dataIndex: "duration", width: 110, customRender: ({ text }: AnyRecord) => formatMs(text) },
  { title: "工具明细", dataIndex: "tools", ellipsis: true },
  { title: "错误信息", dataIndex: "error_message", ellipsis: true },
];

const eventColumns = [
  { title: "时间", dataIndex: "time", width: 120 },
  { title: "类型", dataIndex: "type", width: 180 },
  { title: "Task", dataIndex: "task", width: 220 },
  { title: "Trace", dataIndex: "trace", width: 220 },
  { title: "数据", dataIndex: "data", ellipsis: true },
];

const loadDashboard = async () => {
  loading.value = true;
  errorMessage.value = "";
  try {
    const [dashboardResponse, eventsResponse] = await Promise.all([
      axios.get("/api/observability/dashboard"),
      axios.get("/api/observability/events", { params: { limit: 50 } }),
    ]);
    dashboard.value = dashboardResponse.data?.dashboard || {};
    events.value = eventsResponse.data?.events || [];
    lastUpdated.value = new Date();
  } catch (error: any) {
    errorMessage.value = error.response?.data?.detail || "无法获取可观测数据，请确认后端服务已启动";
  } finally {
    loading.value = false;
  }
};

const setupTimer = () => {
  if (timer) {
    window.clearInterval(timer);
    timer = undefined;
  }
  if (autoRefresh.value) {
    timer = window.setInterval(loadDashboard, 5000);
  }
};

const formatMs = (value: any) => {
  const numberValue = Number(value || 0);
  return `${(numberValue * 1000).toFixed(1)} ms`;
};

const formatPercent = (value: any) => {
  const numberValue = Number(value || 0);
  return `${numberValue.toFixed(1)}%`;
};

const formatRatio = (value: any) => {
  if (value === undefined || value === null) return "-";
  return Number(value).toFixed(2);
};

const formatNumber = (value: any) => {
  if (value === undefined || value === null) return "-";
  return Number(value).toFixed(0);
};

const formatTime = (value: any) => {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleTimeString();
};

watch(autoRefresh, setupTimer);

onMounted(() => {
  loadDashboard();
  setupTimer();
});

onBeforeUnmount(() => {
  if (timer) window.clearInterval(timer);
});
</script>

<style scoped>
.observability-page {
  max-width: 1280px;
  margin: 0 auto;
}

.observability-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 20px;
}

.observability-header h1 {
  margin: 0;
  color: #172033;
  font-size: 28px;
  font-weight: 700;
}

.observability-header p {
  margin: 6px 0 0;
  color: #657089;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
}

.status-alert {
  margin-bottom: 16px;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.metric-card,
.panel {
  background: #ffffff;
  border: 1px solid #e7ebf2;
  border-radius: 8px;
  box-shadow: 0 8px 20px rgba(30, 42, 64, 0.04);
}

.metric-card {
  padding: 16px;
}

.metric-card span {
  display: block;
  color: #657089;
  font-size: 13px;
}

.metric-card strong {
  display: block;
  margin-top: 8px;
  color: #172033;
  font-size: 24px;
  line-height: 1;
}

.panel-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  margin-bottom: 16px;
}

.panel {
  padding: 16px;
  min-width: 0;
}

.panel.full {
  margin-bottom: 16px;
}

.panel-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.panel-title h2 {
  margin: 0;
  color: #172033;
  font-size: 17px;
  font-weight: 700;
}

.panel-title span {
  color: #657089;
  font-size: 13px;
}

.metric-list {
  display: grid;
  gap: 10px;
}

.metric-list div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 0;
  border-bottom: 1px solid #eef1f6;
}

.metric-list div:last-child {
  border-bottom: none;
}

.metric-list span {
  color: #657089;
}

.metric-list strong {
  color: #172033;
}

.raw-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

pre {
  max-height: 320px;
  margin: 0;
  padding: 12px;
  overflow: auto;
  background: #0f172a;
  color: #dbeafe;
  border-radius: 8px;
  font-size: 12px;
}

@media (max-width: 960px) {
  .summary-grid,
  .panel-grid,
  .raw-grid {
    grid-template-columns: 1fr;
  }

  .observability-header {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
