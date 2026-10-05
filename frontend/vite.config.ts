import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      // 只要请求路径以 /api 开头，就转接到后端 FastAPI
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        // 如果后端 api 接口本身没有 /api 前缀，可以开启下面的重写
        // rewrite: (path) => path.replace(/^\/api/, '')
      }
    }
  }
});
