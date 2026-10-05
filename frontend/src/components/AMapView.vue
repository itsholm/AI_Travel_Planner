<!-- components/AMapView.vue -->
<template>
  <div v-if="mapError" role="alert" style="padding: 16px; color: #b42318;">{{ mapError }}</div>
  <div v-show="!mapError" id="amap-container" ref="mapContainer" style="width: 100%; height: 300px;"></div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, watch, ref } from 'vue';
import AMapLoader from '@amap/amap-jsapi-loader';
import { message } from 'ant-design-vue'; // ✅ 修复 message
import type { DayPlan } from '../types/travel';

const props = defineProps<{
  days: DayPlan[];          // ✅ 接收所有天
  activeDayIndex: number;   // ✅ 当前高亮第几天
}>();

const mapError = ref('');
let mapInstance: any = null;
let AMapClass: any = null; //持久化便量存储AMap 类库
const polylines:any[] = [];//全局存储所有路线


// 初始化地图
const initMap = async () => {
  //const mapContainer = document.getElementById('amap-container');
  //if (!mapContainer) return;

  const key = import.meta.env.VITE_AMAP_KEY;
  if (!key) {
    mapError.value = '地图服务尚未配置，请联系维护人员。';
    return;
  }

  try {
    const securityJsCode = import.meta.env.VITE_AMAP_SECURITY_CODE;
    if (securityJsCode) {
      (window as Window & {
        _AMapSecurityConfig?: { securityJsCode: string };
      })._AMapSecurityConfig = { securityJsCode };
    }
    const AMap = await AMapLoader.load({
      key,
      version: '2.0',
      plugins: ['AMap.Marker', 'AMap.Polyline']
    });
    AMapClass = AMap;//保存加载成功的类库实例

    mapInstance = new AMap.Map("amap-container", {
      zoom: 12,
      viewMode: '3D'
    });

    // 绘制所有景点（全局标记）
    drawAllAttractions();

    // 初始高亮第一天
    if (props.days[props.activeDayIndex]) { // ✅ 修复：判断数组长度
      highlightDayRoute(props.days[props.activeDayIndex]);
    }

  } catch (err) {
    mapError.value = '地图加载失败，请检查网络或地图服务配置后刷新页面。';
    console.error('地图加载失败:', err);
    message.error('地图加载失败'); // ✅ 现在可以用了
  }
};

// 绘制所有景点（不带路线）
const  drawAllAttractions = () => {
  if (!mapInstance || !AMapClass) return;
  props.days.forEach((day, dayIndex) => {
    day.attractions.forEach((attr, idx) => {
      if (attr.location?.longitude && attr.location.latitude) {
        new AMapClass.Marker({
          position: [attr.location.longitude, attr.location.latitude],
          map: mapInstance,
          label: {
            content: `<div style="background:#4CAF50;color:white;padding:2px 6px;border-radius:4px;">D${dayIndex+1}-${idx+1}</div>`,
            direction: 'top'
          }
        });
      }
    });
  });
};

// 高亮某一天的路线
const highlightDayRoute = (day: DayPlan) => {
  if (!mapInstance||!AMapClass) return;
  
  // 清除现有路线（不清除标记）
  polylines.forEach(line => mapInstance.remove(line));
  polylines.length = 0;

  // 绘制当前天路线
  const path = day.attractions
    .filter(attr => attr.location?.longitude && attr.location.latitude)
    .map(attr => [attr.location.longitude, attr.location.latitude]);

  if (path.length >= 2) {
    const polyline = new AMapClass.Polyline({
      path,
      map:mapInstance,//核心修复直接在构造函数中指定 map，或者取消下面 setMap 的注释
      strokeColor: '#FF5722',
      strokeWeight: 6,
      strokeOpacity: 0.9,
      showDir: true
    });
  //#polyline.setMap(mapInstance);
    polylines.push(polyline);
    mapInstance.setFitView([polyline]);
  } else if (path.length === 1) {
    mapInstance.setCenter(path[0]);
    mapInstance.setZoom(14);
  }
};

// 监听 activeDayIndex 变化
watch(() => props.activeDayIndex, (newIndex) => {
  if (mapInstance && AMapClass && props.days[newIndex]) {
    highlightDayRoute(props.days[newIndex]);
  }
}, { immediate: false });

onMounted(() => {
  initMap();
});

onUnmounted(() => {
  if (mapInstance) {
    mapInstance.destroy();
  }
});
</script>