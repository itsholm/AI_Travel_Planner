<template>
  <a-card title="旅行任务与可选操作" style="margin: 20px 0">
    <p>任务状态：{{ task?.state || '加载中' }} · {{ task?.current_step }}</p>
    <p style="overflow-wrap: anywhere">任务编号：{{ taskId }}</p>
    <p v-if="error" role="alert">{{ error }}</p>
    <a-button :loading="busy" @click="refresh">刷新状态</a-button>
    <p>酒店预订为模拟演示，不产生真实订单或扣款。普通行程规划无需审批。</p>
    <template v-if="task?.state === 'COMPLETED' && !task?.result?.booking">
      <a-select v-model:value="selectedDay" placeholder="选择入住日期" style="width: 300px">
        <a-select-option v-for="day in hotelDays" :key="day.day_index" :value="day.day_index">
          {{ day.date }} · {{ day.hotel.name }}
        </a-select-option>
      </a-select>
      <a-input v-model:value="guest" placeholder="入住人姓名（演示用）" style="width: 220px; margin: 8px" />
      <a-button :disabled="selectedDay === undefined || !guest.trim()" :loading="busy" @click="propose">
        生成模拟预订提案
      </a-button>
    </template>
    <div v-if="task?.pending_approval">
      <p>请核对以下单晚预订信息后再确认：</p>
      <p>{{ preview.hotel_name }} · {{ preview.hotel_address }}</p>
      <p>{{ preview.check_in }} 入住，{{ preview.check_out }} 退房；入住人：{{ preview.guest_names?.join('、') }}</p>
      <p>参考费用：¥{{ preview.estimated_cost }}（行程估算，非可成交报价）</p>
      <a-button type="primary" :loading="busy" @click="decide('approve')">确认模拟预订</a-button>
      <a-button :disabled="busy" @click="decide('reject')" style="margin-left: 8px">拒绝预订，保留行程</a-button>
    </div>
    <p v-if="task?.result?.booking">预订操作结果：{{ task.result.booking.status }}</p>
    <a-button v-if="task?.state === 'FAILED'" :loading="busy" @click="resume">从已保存阶段继续</a-button>
  </a-card>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import axios from 'axios';
const props = defineProps<{ taskId: string }>();
const task = ref<any>(null);
const busy = ref(false);
const error = ref('');
const guest = ref('');
const selectedDay = ref<number>();
const hotelDays = computed(() => (task.value?.result?.plan?.days || []).filter((d: any) => d.hotel));
const preview = computed(() => task.value?.pending_approval?.preview?.arguments || {});
async function request(suffix = '', body?: unknown) {
  const id = props.taskId;
  busy.value = true;
  error.value = '';
  try {
    const url = `/api/travel/tasks/${id}${suffix}`;
    const response = suffix ? await axios.post(url, body) : await axios.get(url);
    if (props.taskId === id) task.value = response.data;
  } catch (e: any) {
    if (props.taskId === id) error.value = e.response?.data?.detail || '操作失败，请重试';
  } finally { busy.value = false; }
}
const refresh = () => request();
const resume = () => request('/resume');
const propose = () => request('/booking-proposal', { day_index: selectedDay.value, guest_names: [guest.value.trim()] });
const decide = (decision: string) => request(`/approvals/${task.value.pending_approval.approval_id}/${decision}`);
watch(() => props.taskId, () => { task.value = null; selectedDay.value = undefined; guest.value = ''; refresh(); }, { immediate: true });
</script>
