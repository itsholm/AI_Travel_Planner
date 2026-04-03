<!-- components/TravelResult.vue -->

<template>
  <div class="travel-result-container">
    <!-- 顶部操作栏 -->
    <div class="header-actions mb-4">
      <a-space size="middle">
        <!-- AI 智能修改按钮 -->
        <a-button
          type="primary"
          @click="$emit('modify')"
          :disabled="!sessionId">
          <template #icon>
            <RobotOutlined />
          </template #icon>
          🤖 智能修改
        </a-button>

        <a-button
          type="default"
          @click="toggleEditMode">
          <template #icon>
            <SaveOutlined v-if="editMode" />
            <EditOutlined v-else />
          </template #icon>
          {{ editMode ? '💾 保存修改' : '✏️ 手动编辑' }}
        </a-button>

        <a-dropdown v-if="!editMode">
          <template #overlay>
            <a-menu>
              <a-menu-item key="image" @click="exportAsImage">
                📷 导出为图片
              </a-menu-item>
              <a-menu-item key="pdf" @click="exportAsPDF">
                📄 导出为PDF
              </a-menu-item>
            </a-menu>
          </template #icon>
          <a-button type="default">
            📥 导出行程 <DownOutlined />
          </a-button>
        </a-dropdown>

        <a-button
          type="default"
          danger
          @click="$emit('back')"
        >
          <template #icon>
            <CloseOutlined />
          </template #icon>
          返回规划
        </a-button>
      </a-space>
    </div>

    <!-- 顶部四宫格：概览 + 预算 + 地图 + 天气 -->
    <a-row :gutter="20" class="top-grid">
      <!-- 行程概览 -->
      <a-col :xs="24" :md="6">
        <a-card title="📋 行程概览" :bordered="false" class="overview-card">
          <div class="overview-content">
            <div class="info-item">
              <span class="info-label">📅 日期：</span>
              <span class="info-value">{{ plan.start_date }} 至 {{ plan.end_date }}</span>
            </div>
            <div class="info-item">
              <span class="info-label">💡 建议：</span>
              <span class="info-value">{{ plan.overall_suggestions }}</span>
            </div>
          </div>
        </a-card>
      </a-col>

      <!-- 预算明细 -->
      <a-col :xs="24" :md="6">
        <a-card title="💰 预算明细" :bordered="false" class="budget-card">
          <div class="budget-grid">
            <div class="budget-item">
              <div class="budget-label">景点门票</div>
              <div class="budget-value">¥{{ plan.budget?.total_attractions }}</div>
            </div>
            <div class="budget-item">
              <div class="budget-label">酒店住宿</div>
              <div class="budget-value">¥{{ plan.budget?.total_hotels}}</div>
            </div>
            <div class="budget-item">
              <div class="budget-label">餐饮费用</div>
              <div class="budget-value">¥{{ plan.budget?.total_meals }}</div>
            </div>
            <div class="budget-item">
              <div class="budget-label">交通费用</div>
              <div class="budget-value">¥{{ plan.budget?.total_transportation}}</div>
            </div>
          </div>
          <div class="budget-total">
            <span class="total-label">预估总费用</span>
            <span class="total-value">¥{{ plan.budget?.total || 0 }}</span>
          </div>
        </a-card>
      </a-col>

      <!-- 景点地图 -->
      <a-col :xs="24" :md="6">
        <a-card title="📍 景点地图" :bordered="false" class="map-card">
          <AMapView 
            :days="plan.days" 
            :active-day-index="activeDayIndex"
            @day-change="handleDayChange"
          />
        </a-card>
      </a-col>

      <!-- 天气信息 -->
      <a-col :xs="24" :md="6">
        <a-card title="🌤️ 天气预报" :bordered="false" class="weather-card">
          <a-row :gutter="8">
            <a-col 
              v-for="weather in plan.weather_info" 
              :key="weather.date"
              :xs="24"
              :sm="12"
            >
              <div class="weather-item">
                <div class="weather-date">{{ weather.date }}</div>
                <div class="weather-temp">{{ weather.day_temp }}°C / {{ weather.night_temp }}°C</div>
                <div class="weather-desc">{{ weather.day_weather }} | {{ weather.wind_direction }} {{ weather.wind_power }}</div>
              </div>
            </a-col>
          </a-row>
        </a-card>
      </a-col>
    </a-row>
    <div class="day-switcher mb-4">
      <span class="switch-label">📍 路线切换：</span> 
      <a-radio-group v-model:value="activeDayIndex" size="small"> <!--绑定属性是 value,必须使用 v-model:value-->
        <a-radio-button v-for="(day, index) in plan.days" :key="index" :value="index">
            第{{ day.day_index }}天
        </a-radio-button>
      </a-radio-group>
    </div>

    <!-- 每日行程（折叠式） -->
    <a-card title="📅 每日行程" :bordered="false" class="days-card">
      <a-collapse v-model:activeKey="activeDays" accordion>
        <a-collapse-panel
          v-for="(day, index) in plan.days"
          :key="index"
          :id="`day-${index}`"
        >
          <template #header>
            <div class="day-header">
              <span class="day-title">第{{ day.day_index }}天</span>
              <span class="day-date">{{ day.date }}</span>
              <a-tag color="orange" class="weather-tag">
                🌤 {{ day.weather }}
              </a-tag>
            </div>
          </template #icon>

          <!-- 行程基本信息 -->
          <div class="day-info">
            <div class="info-row">
              <span class="label">📝 行程描述:</span>
              <span class="value">{{ day.description }}</span>
            </div>
            <div class="info-row">
              <span class="label">🚗 交通方式:</span>
              <span class="value">{{ day.transportation }}</span>
            </div>
            <div class="info-row">
              <span class="label">🏨 住宿:</span>
              <span class="value">{{ day.accommodation }}</span>
            </div>
          </div>

          <!-- 景点安排 -->
          <a-divider orientation="left">🎯 景点安排</a-divider>
          <a-list
            :data-source="day.attractions"
            :grid="{ gutter: 16, column: 2 }"
          >
            <template #renderItem="{ item, index }">
              <a-list-item>
                <a-card :title="item.name" size="small" class="attraction-card">
                  <template #extra v-if="editMode">
                    <a-space>
                      <a-button size="small" @click="moveAttraction(day.day_index, index, 'up')" :disabled="index === 0">↑</a-button>
                      <a-button size="small" @click="moveAttraction(day.day_index, index, 'down')" :disabled="index === day.attractions.length - 1">↓</a-button>
                      <a-button size="small" danger @click="deleteAttraction(day.day_index, index)">✕</a-button>
                    </a-space>
                  </template #icon>
                  <!-- 景点图片 -->
                  <div class="attraction-image-wrapper">
                    <img
                      :src="attractionPhotos[item.name] || item.image_url || getPlaceholderImage(item.name)"
                      :alt="item.name"
                      class="attraction-image"
                      @error="handleImageError"
                    />
                    <div class="attraction-badge">
                      <span class="badge-number">{{ index + 1 }}</span>
                    </div>
                    <div v-if="item.ticket_price" class="price-tag">
                      ¥{{ item.ticket_price }}
                    </div>
                  </div>

                  <div v-if="editMode">
                    <a-input v-model:value="item.name" placeholder="景点名称" class="mb-2" />
                    <a-textarea v-model:value="item.description" placeholder="景点描述" :rows="2" />
                  </div>
                  
                  <div v-else>
                  <!-- 景点信息 -->
                    <p><strong>地址:</strong> {{ item.address }}</p>
                    <p><strong>游览时长:</strong> {{ item.visit_duration }}分钟</p>
                    <p><strong>描述:</strong> {{ item.description }}</p>
                    <p v-if="item.rating"><strong>评分:</strong> {{ item.rating }}⭐</p>
                  </div>
                </a-card>
              </a-list-item>
            </template #icon>
          </a-list>

          <!-- 酒店推荐 -->
          <a-divider v-if="day.hotel" orientation="left">🏨 住宿推荐</a-divider>
          <a-card v-if="day.hotel" size="small" class="hotel-card">
            <template #title>
              <span class="hotel-title">{{ day.hotel.name }}</span>
            </template #icon>
            <a-descriptions :column="2" size="small">
              <a-descriptions-item label="地址">{{ day.hotel.address }}</a-descriptions-item>
              <a-descriptions-item label="类型">{{ day.hotel.type }}</a-descriptions-item>
              <a-descriptions-item label="价格范围">{{ day.hotel.price_range }}</a-descriptions-item>
              <a-descriptions-item label="评分">{{ day.hotel.rating }}⭐</a-descriptions-item>
              <a-descriptions-item label="距离" :span="2">{{ day.hotel.distance }}</a-descriptions-item>
            </a-descriptions>
          </a-card>

          <!-- 餐饮安排 -->
          <a-divider orientation="left">🍽️ 餐饮安排</a-divider>
          <a-descriptions :column="1" bordered size="small">
            <a-descriptions-item
              v-for="meal in day.meals"
              :key="meal.type"
              :label="getMealLabel(meal.type)"
            >
              {{ meal.name }}
              <span v-if="meal.description"> - {{ meal.description }}</span>
            </a-descriptions-item>
          </a-descriptions>
        </a-collapse-panel>
      </a-collapse>
    </a-card>
  </div>
  
  <!-- AI 修改对话框 -->
  <a-modal
    v-model:open="showModifyDialog"
    title="🤖 智能修改行程"
    @ok="handleModify"
    @cancel="showModifyDialog = false"
    :confirm-loading="modifyLoading"
    width="600px"
  >
    <div class="modify-dialog-content">
      <p class="modify-hint">
        请告诉我您想如何调整行程，系统会根据您的建议智能优化：
      </p>

      <ul class="modify-examples">
        <li>• 把第二天的景点换成天坛</li>
        <li>• 增加第三天的午餐预算到100元</li>
        <li>• 调整住宿为豪华酒店</li>
        <li>• 添加附近的博物馆</li>
      </ul>

      <a-textarea
        v-model:value="modifyText"
        placeholder="请输入您的修改要求，越具体越好..."
        :rows="4"
        :max-length="500"
        show-count
        class="modify-input"
      />

      <!-- 显示对话历史 -->
      <div v-if="conversationHistory.length > 0" class="conversation-history">
        <h4>💬 最近对话</h4>
        <div class="history-list">
          <div
            v-for="(msg, index) in conversationHistory.slice(-3)"
            :key="index"
            class="history-item"
            :class="msg.role"
          >
            <strong>{{ msg.role === 'user' ? '您' : '助手' }}:</strong>
            <span>{{ msg.content }}</span>
          </div>
        </div>
      </div>
    </div>
  </a-modal>
</template #icon>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { message } from 'ant-design-vue';
import { EditOutlined, SaveOutlined, DownOutlined, RobotOutlined, CloseOutlined } from '@ant-design/icons-vue';
import type { TravelPlan } from '../types/travel';
import AMapView from './AMapView.vue';

const props = defineProps<{
  plan: TravelPlan
  sessionId?: string
}>();

const emit = defineEmits<{
  back: []
  modify: []
}>();

const editMode = ref(false);
//const originalPlan = ref<TravelPlan | null>(null);
const activeDays = ref<number[]>([0]); // 默认展开第一天
const activeDayIndex = ref(0); // 当前高亮的天数索引


// 图片缓存
const attractionPhotos = ref<Record<string, string>>({});

// 加载景点图片（保留原有逻辑）
const loadAttractionPhotos = async () => {
  if (!props.plan?.days) return;

  const promises: Promise<void>[] = [];
  props.plan.days.forEach(day => {
    day.attractions.forEach(attraction => {
      if (attractionPhotos.value[attraction.name]) return;
      
      const promise = fetch(`/api/poi/photo?name=${encodeURIComponent(attraction.name)}`)
        .then(res => res.json())
        .then(data => {
          if (data.success && data.data.photo_url) {
            attractionPhotos.value[attraction.name] = data.data.photo_url;
          }
        })
        .catch(err => {
          console.warn(`图片加载失败: ${attraction.name}`, err);
        });
      promises.push(promise);
    });
  });

  await Promise.all(promises);
};

onMounted(() => {
  loadAttractionPhotos();
});

  // 切换编辑模式
  const toggleEditMode = () => {
    if (editMode.value) {
      // 保存修改
      emit('save', props.plan)
      message.success('修改已保存')
    } else {
      // 进入编辑模式，保存原始数据
      //originalPlan.value = JSON.parse(JSON.stringify(props.plan))
      message.info('进入编辑模式，可以调整景点顺序')
    }
    editMode.value = !editMode.value
  }
  
  // 移动景点
  const moveAttraction = (dayIndex: number, attrIndex: number, direction: 'up' | 'down') => {
    const day = props.plan.days.find(d => d.day_index === dayIndex)
    if (!day) return
  
    if (direction === 'up' && attrIndex > 0) {
      [day.attractions[attrIndex], day.attractions[attrIndex - 1]] = 
      [day.attractions[attrIndex - 1], day.attractions[attrIndex]]
      message.success('景点已上移')
    } else if (direction === 'down' && attrIndex < day.attractions.length - 1) {
      [day.attractions[attrIndex], day.attractions[attrIndex + 1]] = 
      [day.attractions[attrIndex + 1], day.attractions[attrIndex]]
      message.success('景点已下移')
    }
  }
  
  // 删除景点
  const deleteAttraction = (dayIndex: number, attrIndex: number) => {
    const day = props.plan.days.find(d => d.day_index === dayIndex)
    if (!day) return
  
    if (day.attractions.length <= 1) {
      message.warning('每天至少需要保留一个景点')
      return
    }
  
    day.attractions.splice(attrIndex, 1)
    message.success('景点已删除')
  }
  

// 地图按天切换
const handleDayChange = (index: number) => {
  activeDayIndex.value = index;
};

// 工具函数
const getMealLabel = (type: string): string => {
  const labels: Record<string, string> = {
    breakfast: '早餐',
    lunch: '午餐',
    dinner: '晚餐',
    snack: '小吃'
  };
  return labels[type] || type;
};

const getPlaceholderImage = (name: string) => {
  return `https://via.placeholder.com/400x300?text=${encodeURIComponent(name)}`;
};

const handleImageError = (e: Event) => {
  const img = e.target as HTMLImageElement;
  img.src = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="400" height="300"%3E%3Crect width="400" height="300" fill="%23f0f0f0"/%3E%3Ctext x="50%25" y="50%25" dominant-baseline="middle" text-anchor="middle" font-family="sans-serif" font-size="18" fill="%23999"%3E图片加载失败%3C/text%3E%3C/svg%3E';
};

// 导出占位
const exportAsImage = () => message.info('导出为图片（开发中）');
const exportAsPDF = () => message.info('导出为PDF（开发中）');

// AI 修改相关功能
type ChatMessage = { role: 'user' | 'assistant'; content: string };

const showModifyDialog = ref(false);
const modifyLoading = ref(false);
const modifyText = ref('');
const conversationHistory = ref<ChatMessage[]>([]);

// 点击“智能修改”由父组件接管 AI 逻辑（本组件只负责弹窗壳和基本交互）
const handleModify = async () => {
  showModifyDialog.value = false;
  emit('modify');
};

// 兼容旧命名（如果你后续在模板里切到 handleModifyClick）
const handleModifyClick = () => {
  showModifyDialog.value = true;
};
</script>

<style scoped>
.travel-result-container {
  background: white;
  border-radius: 16px;
  padding: 24px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.08);
}

.mb-4 { margin-bottom: 16px; }

/* 顶部四宫格 */
.top-grid {
  margin-bottom: 24px;
}

.overview-card, .budget-card, .map-card, .weather-card {
  height: 100%;
}

.overview-content {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.info-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.info-label {
  font-size: 14px;
  font-weight: 600;
  color: #666;
}
.info-value {
  font-size: 15px;
  color: #333;
  line-height: 1.6;
}

.budget-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
  margin-bottom: 16px;
}
.budget-item {
  text-align: center;
  padding: 12px;
  background: linear-gradient(135deg, #f5f7fa 0%, #ffffff 100%);
  border-radius: 8px;
  border: 1px solid #e8e8e8;
}
.budget-label {
  font-size: 13px;
  color: #666;
  margin-bottom: 8px;
}
.budget-value {
  font-size: 20px;
  font-weight: 700;
  color: #1890ff;
}
.budget-total {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 8px;
  color: white;
}
.total-label { font-size: 16px; font-weight: 600; }
.total-value { font-size: 28px; font-weight: 700; }

.map-card :deep(.ant-card-body) {
  height: 300px;
  padding: 0;
}

/* 天气卡片 */
.weather-card {
  margin-bottom: 24px;
}
.weather-item {
  padding: 12px;
  background: #f8f9fa;
  border-radius: 8px;
  margin-bottom: 12px;
}
.weather-date {
  font-size: 14px;
  font-weight: 600;
  color: #00796b;
  margin-bottom: 6px;
}
.weather-temp {
  font-size: 16px;
  font-weight: 700;
  color: #1890ff;
  margin-bottom: 4px;
}
.weather-desc {
  font-size: 12px;
  color: #666;
}

/* 每日行程 */
.days-card {
  margin-top: 24px;
}

.day-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}
.day-title {
  font-size: 18px;
  font-weight: 600;
  color: #333;
}
.day-date {
  font-size: 14px;
  color: #999;
}
.weather-tag {
  font-size: 14px;
  padding: 4px 12px;
}

.day-info {
  margin-bottom: 20px;
  padding: 16px;
  background: linear-gradient(135deg, #f5f7fa 0%, #ffffff 100%);
  border-radius: 8px;
  border: 1px solid #e8e8e8;
}
.info-row {
  display: flex;
  gap: 12px;
  margin-bottom: 8px;
}
.label {
  font-weight: 600;
  color: #666;
  min-width: 100px;
}
.value {
  color: #333;
  flex: 1;
}

/* 景点卡片 */
.attraction-image-wrapper {
  position: relative;
  margin-bottom: 12px;
  border-radius: 8px;
  overflow: hidden;
}
.attraction-image {
  width: 100%;
  height: 200px;
  object-fit: cover;
  transition: transform 0.3s ease;
}
.attraction-badge {
  position: absolute;
  top: 12px;
  left: 12px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: bold;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
}
.badge-number { font-size: 18px; }
.price-tag {
  position: absolute;
  top: 12px;
  right: 12px;
  background: rgba(255, 77, 79, 0.9);
  color: white;
  padding: 4px 12px;
  border-radius: 12px;
  font-weight: bold;
  font-size: 14px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
}

@media (max-width: 768px) {
  .top-grid {
    flex-direction: column;
  }
  .weather-card .weather-item {
    padding: 10px;
  }
}

/* AI 修改对话框样式 */
.modify-dialog-content {
  padding: 8px 0;
}

.modify-hint {
  margin-bottom: 16px;
  color: #666;
  font-size: 14px;
}

.modify-examples {
  margin-bottom: 20px;
  padding-left: 20px;
}

.modify-examples li {
  margin-bottom: 8px;
  color: #666;
  font-size: 13px;
}

.modify-input {
  margin-bottom: 20px;
}

.conversation-history {
  margin-top: 20px;
  padding-top: 20px;
  border-top: 1px solid #f0f0f0;
}

.conversation-history h4 {
  margin-bottom: 12px;
  color: #666;
  font-size: 14px;
}

.history-list {
  max-height: 200px;
  overflow-y: auto;
}

.history-item {
  margin-bottom: 12px;
  padding: 12px;
  background: #f8f9fa;
  border-radius: 8px;
  font-size: 13px;
  line-height: 1.5;
}

.history-item.user {
  background: #e3f2fd;
  margin-left: 20px;
}

.history-item.assistant {
  background: #f3e5f5;
  margin-right: 20px;
}

.history-item strong {
  display: inline-block;
  margin-right: 8px;
  font-weight: 600;
}
</style>