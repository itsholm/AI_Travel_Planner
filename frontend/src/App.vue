<!-- App.vue -->
<template>
  <div class="layout-container">
    <a-layout-content class="content">
      <!-- 装饰背景 -->
      <div class="bg-decoration">
        <div class="circle circle-1"></div>
        <div class="circle circle-2"></div>
      </div>

      <!-- 页面头部（表单） -->
      <div v-if="!finalPlan" class="page-header">
        <h1 class="page-title">定制你的专属行程</h1>
        <p class="page-subtitle">基于多 Agent 协作系统，为您提供最专业的旅行建议</p>
      </div>

      <a-card v-if="!finalPlan" class="form-card" :bordered="false">
        <a-form :model="formData" layout="vertical" @finish="handleSubmit">
          <!-- 目的地与日期 -->
          <div class="form-section">
            <div class="section-header">
              <span class="section-icon">📍</span>
              <span class="section-title">目的地与日期</span>
            </div>
            <a-row :gutter="24">
              <a-col :span="8">
                <a-form-item label="目的地城市" name="city" :rules="[{ required: true }]">
                  <a-input v-model:value="formData.city" placeholder="例如: 北京" size="large" />
                </a-form-item>
              </a-col>
              <a-col :span="6">
                <a-form-item label="开始日期" name="start_date" :rules="[{ required: true }]">
                  <a-date-picker
                    v-model:value="formData.start_date"
                    :disabled-date="disabledDate"
                    style="width: 100%"
                    size="large"
                    @change="onStartDateChange"
                  />
                </a-form-item>
              </a-col>
              <a-col :span="6">
                <a-form-item label="结束日期" name="end_date" :rules="[{ required: true }]">
                  <a-date-picker
                    v-model:value="formData.end_date"
                    :disabled-date="disabledDate"
                    style="width: 100%"
                    size="large"
                    @change="onEndDateChange"
                  />
                </a-form-item>
              </a-col>
              <a-col :span="4">
                <a-form-item label="旅行天数">
                  <div class="days-badge">{{ travelDays }} 天</div>
                </a-form-item>
              </a-col>
            </a-row>
          </div>

          <!-- 偏好设置 -->
          <div class="form-section">
            <div class="section-header">
              <span class="section-icon">⚙️</span>
              <span class="section-title">偏好设置</span>
            </div>
            <a-row :gutter="24">
              <a-col :span="8">
                <a-form-item label="交通方式">
                  <a-select v-model:value="formData.transportation" size="large">
                    <a-select-option value="公共交通">🚇 公共交通</a-select-option>
                    <a-select-option value="自驾">🚗 自驾</a-select-option>
                    <a-select-option value="步行">🚶 步行</a-select-option>
                  </a-select>
                </a-form-item>
              </a-col>
              <a-col :span="8">
                <a-form-item label="住宿偏好">
                  <a-select v-model:value="formData.accommodation" size="large">
                    <a-select-option value="经济型酒店">💰 经济型</a-select-option>
                    <a-select-option value="舒适型酒店">🏨 舒适型</a-select-option>
                    <a-select-option value="豪华酒店">⭐ 豪华型</a-select-option>
                  </a-select>
                </a-form-item>
              </a-col>
              <a-col :span="8">
                <a-form-item label="旅行标签">
                  <a-checkbox-group v-model:value="formData.preferences">
                    <a-checkbox value="历史文化">🏛️ 历史</a-checkbox>
                    <a-checkbox value="自然风光">🏞️ 自然</a-checkbox>
                    <a-checkbox value="美食">🍜 美食</a-checkbox>
                  </a-checkbox-group>
                </a-form-item>
              </a-col>
            </a-row>
          </div>

          <!-- 额外要求 -->
          <div class="form-section">
            <div class="section-header">
              <span class="section-icon">💬</span>
              <span class="section-title">额外要求</span>
            </div>
            <a-form-item name="free_text_input">
              <a-textarea
                v-model:value="formData.free_text_input"
                placeholder="例如：想看升旗、海鲜过敏..."
                :rows="3"
              />
            </a-form-item>
          </div>

          <a-button
            type="primary"
            html-type="submit"
            :loading="loading"
            size="large"
            block
            class="submit-btn"
          >
            🚀 开始 AI 智能规划
          </a-button>
        </a-form>
      </a-card>

      <!-- 加载中 -->
      <div v-if="loading" class="loading-area">
        <a-spin size="large" tip="AI 专家团正在为您搜索景点、查询天气并生成行程..." />
      </div>

      <!-- 结果页 -->
      <TravelResult
        v-if="finalPlan"
        :plan="finalPlan"
        :session-id="sessionId"
        @back="handleBack"
        @day-change="activeDayIndex= $event"
        @modify="openModifyDialog"
      />

      <!-- 修改行程对话框 -->
      <a-modal
        v-model:open="showModifyDialog"
        title="修改行程"
        @ok="handleModify"
        @cancel="showModifyDialog = false"
        :confirm-loading="modifyLoading"
      >
        <p class="modify-hint">请告诉我您想如何调整行程，例如：</p>
        <ul class="modify-examples">
          <li>把第二天的景点换成天坛</li>
          <li>增加第三天的午餐预算到100元</li>
          <li>调整住宿为豪华酒店</li>
        </ul>
        <a-textarea
          v-model:value="modifyText"
          placeholder="请输入您的修改要求..."
          :rows="4"
          :max-length="200"
          show-count
        />

        <!-- 显示对话历史 -->
        <div v-if="conversationHistory.length > 0" class="conversation-history">
          <h4>对话历史</h4>
          <div v-for="(msg, index) in conversationHistory.slice(-3)" :key="index" class="history-item">
            <span class="history-role">{{ msg.role === 'user' ? '👤 您' : '🤖 助手' }}:</span>
            <span class="history-content">{{ msg.content }}</span>
          </div>
        </div>
      </a-modal>
    </a-layout-content>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed,onMounted } from 'vue';
import axios from 'axios';
import { message } from 'ant-design-vue';
import dayjs, { Dayjs } from 'dayjs';
import type { TravelPlan } from './types/travel';

// 导入组件
import TravelResult from './components/TravelResult.vue';

const loading = ref(false);
const finalPlan = ref<TravelPlan | null>(null);
const activeDayIndex = ref(0);
const sessionId = ref<string>("");  // 会话ID
const conversationHistory = ref<any[]>([]);  // 对话历史

// 表单数据
const formData = reactive({
  city: '',
  start_date: null as Dayjs | null,
  end_date: null as Dayjs | null,
  transportation: '公共交通',
  accommodation: '舒适型酒店',
  preferences: [] as string[],
  free_text_input: ''
});

// 日期限制
const disabledDate = (current: Dayjs) => {
  return current && current < dayjs().startOf('day');
};

// 自动计算天数（含边界检查）
const travelDays = computed(() => {
  if (!formData.start_date || !formData.end_date) return 0;
  const diff = dayjs(formData.end_date).diff(dayjs(formData.start_date), 'day') + 1;
  return Math.min(diff, 30); // 最长30天
});

// 日期变更处理
const onStartDateChange = () => {
  if (formData.start_date && formData.end_date) {
    const maxEndDate = dayjs(formData.start_date).add(29, 'day'); // 最多30天
    if (dayjs(formData.end_date).isAfter(maxEndDate)) {
      formData.end_date = maxEndDate;
      message.warning('行程最长30天，已自动调整结束日期');
    }
  }
};

const onEndDateChange = () => {
  if (formData.start_date && formData.end_date) {
    const diff = dayjs(formData.end_date).diff(dayjs(formData.start_date), 'day') + 1;
    if (diff > 30) {
      formData.end_date = dayjs(formData.start_date).add(29, 'day');
      message.warning('行程最长30天，已自动调整结束日期');
    }
  }
};

// 页面加载时尝试恢复数据
onMounted(() => {
  const savedPlan = sessionStorage.getItem('travel_plan');
  const savedActiveDay = sessionStorage.getItem('active_day_index');
  const savedSessionId = sessionStorage.getItem('session_id');

  if (savedPlan) {
    try {
      finalPlan.value = JSON.parse(savedPlan);
      console.log('💾 已恢复保存的行程数据');
    } catch (e) {
      console.error('❌ 恢复数据失败:', e);
    }
  }

  if (savedActiveDay) {
    activeDayIndex.value = parseInt(savedActiveDay);
  }

  if (savedSessionId) {
    sessionId.value = savedSessionId;
    console.log('💾 已恢复会话ID:', sessionId.value);
  }
});

// 保存数据到 sessionStorage
const savePlanToSession = (plan: TravelPlan) => {
  sessionStorage.setItem('travel_plan', JSON.stringify(plan));
  sessionStorage.setItem('active_day_index', activeDayIndex.value.toString());
  if (sessionId.value) {
    sessionStorage.setItem('session_id', sessionId.value);
  }
};

// 清除保存的数据
const clearSavedPlan = () => {
  sessionStorage.removeItem('travel_plan');
  sessionStorage.removeItem('active_day_index');
  sessionStorage.removeItem('session_id');
};
// 提交处理
const handleSubmit = async () => {
    // 清除旧数据
    clearSavedPlan();
  if (travelDays.value > 30) {
    message.warning('智能规划目前仅支持最长 30 天的行程，系统将为您规划前 30 天的内容。');
  }

  loading.value = true;
  finalPlan.value = null;

  const requestData = {
    ...formData,
    start_date: formData.start_date ? dayjs(formData.start_date).format('YYYY-MM-DD') : '',
    end_date: formData.end_date ? dayjs(formData.end_date).format('YYYY-MM-DD') : '',
    travel_days: travelDays.value
  };

  try {
    const response = await axios.post('/api/plan', requestData, {
      timeout: 120000
    });
    console.log('📥 后端返回数据:', response.data);
    console.log('💰 预算数据:', response.data.budget);

    if (response.data) {
      finalPlan.value = response.data;
      sessionId.value = response.data.session_id || "";  // 保存会话ID
      console.log('💾 会话ID:', sessionId.value);
      message.success('规划生成成功！');
    }
  } catch (error: any) {
    console.error('API Error:', error);
    if (error.response) {
      message.error(error.response.data?.message || '服务器错误');
    } else {
      message.error('网络连接失败，请检查后端服务');
    }
  } finally {
    loading.value = false;
  }
};

// 返回处理
const handleBack = () => {
  finalPlan.value = null;
  sessionId.value = "";
  clearSavedPlan(); // 清除保存的数据
};

// 修改行程功能
const showModifyDialog = ref(false);
const modifyText = ref("");
const modifyLoading = ref(false);

const openModifyDialog = () => {
  if (!sessionId.value) {
    message.error('会话已失效，请重新规划行程');
    return;
  }
  showModifyDialog.value = true;

  // 加载对话历史
  loadConversationHistory();
};

const handleModify = async () => {
  if (!sessionId.value) {
    message.error('会话已失效，请重新规划行程');
    return;
  }

  if (!modifyText.value.trim()) {
    message.warning('请输入修改要求');
    return;
  }

  modifyLoading.value = true;

  try {
    const response = await axios.post('/api/modify', {
      session_id: sessionId.value,
      instruction: modifyText.value.trim()
    });

    if (response.data) {
      finalPlan.value = response.data;
      message.success('行程已修改！');
      savePlanToSession(finalPlan.value);

      // 更新对话历史
      if (response.data.current_plan) {
        loadConversationHistory();
      }
    }

    showModifyDialog.value = false;
    modifyText.value = "";
  } catch (error: any) {
    console.error('Modify Error:', error);
    if (error.response) {
      message.error(error.response.data?.message || '修改失败');
    } else {
      message.error('网络连接失败，请检查后端服务');
    }
  } finally {
    modifyLoading.value = false;
  }
};

const loadConversationHistory = async () => {
  if (!sessionId.value) return;

  try {
    const response = await axios.get(`/api/session/${sessionId.value}`);
    if (response.data && response.data.messages) {
      conversationHistory.value = response.data.messages;
      console.log('💾 对话历史已加载:', conversationHistory.value);
    }
  } catch (error: any) {
    console.error('加载对话历史失败:', error);
  }
};
</script>

<style scoped>
.layout-container {
  min-height: 100vh;
  background: #f4f7f9;
  position: relative;
  overflow: hidden;
}

.content {
  padding: 40px 50px;
  position: relative;
  z-index: 1;
}

/* 装饰背景 */
.bg-decoration {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  z-index: 0;
}
.circle {
  position: absolute;
  border-radius: 50%;
  background: linear-gradient(135deg, #e0eafc 0%, #cfdef3 100%);
  opacity: 0.5;
}
.circle-1 { width: 400px; height: 400px; top: -100px; right: -100px; }
.circle-2 { width: 300px; height: 300px; bottom: -50px; left: -50px; }

.page-header {
  text-align: center;
  margin-bottom: 40px;
}
.page-title { font-size: 32px; font-weight: 800; color: #1a1a1a; margin-bottom: 8px; }
.page-subtitle { color: #666; font-size: 16px; }

.form-card {
  max-width: 900px;
  margin: 0 auto;
  border-radius: 16px;
  box-shadow: 0 10px 25px rgba(0,0,0,0.05);
}
.form-section {
  margin-bottom: 30px;
  padding: 20px;
  background: #fafafa;
  border-radius: 12px;
}
.section-header {
  margin-bottom: 20px;
  display: flex;
  align-items: center;
}
.section-icon { font-size: 20px; margin-right: 10px; }
.section-title { font-size: 17px; font-weight: 600; color: #333; }

.days-badge {
  background: #e6f7ff;
  color: #1890ff;
  padding: 8px 16px;
  border-radius: 8px;
  font-weight: bold;
  text-align: center;
  border: 1px solid #91d5ff;
}
.submit-btn { height: 50px; font-size: 18px; border-radius: 12px; margin-top: 20px; }

.loading-area { text-align: center; margin-top: 50px; }

@media (max-width: 768px) {
  .content {
    padding: 20px 16px;
  }
  .form-card {
    padding: 16px;
  }
  .page-header {
    padding: 0 16px;
  }
}
</style>